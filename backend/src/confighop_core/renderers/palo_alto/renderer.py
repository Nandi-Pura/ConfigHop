import os
import tempfile
from copy import deepcopy
from collections.abc import Callable
from hashlib import sha256
from pathlib import Path
from xml.etree import ElementTree as ET

from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException

from ...compatibility import AssessmentStatus, assess
from ...errors import ConfigParseError
from ...hardware.registry import get_profile
from ...palo_alto_constants import NATIVE_QSFP_SPEED_XML
from ...models.hardware import HardwareProfile, RequiredCondition, TargetRenderSupport
from ...models.inventory import PaloAltoInventory
from ...models.mapping import MigrationPreview, PreviewStatus, Severity
from ...models.transformation import (
    CandidateRenderResult, CandidateValidationReport, OperationType, RenderFinding,
    SemanticChange, SemanticMigrationDiff, TransformationPlan,
)
from ...parsers.palo_alto.parser import MAX_XML_BYTES, parse_palo_alto_xml
from ...transformation import build_transformation_plan
from ...validation import expected_inventory, preservation_audit
from ...validation.candidate import element_path
from .locators import locate
from .references import unmodeled_interface_references


class RenderFailure(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class CandidateLimitExceeded(Exception):
    pass


def _safe_tree(data: bytes) -> ET.Element:
    if len(data) > MAX_XML_BYTES:
        raise RenderFailure("SOURCE_INVENTORY_MISMATCH")
    try:
        SafeET.fromstring(data, forbid_dtd=True, forbid_entities=True, forbid_external=True)
        parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True, insert_pis=True))
        root = ET.fromstring(data, parser=parser)
    except (ET.ParseError, DefusedXmlException) as exc:
        raise RenderFailure("SOURCE_INVENTORY_MISMATCH") from exc
    if root.tag != "config":
        raise RenderFailure("SOURCE_INVENTORY_MISMATCH")
    return root


def _blocked(plan: TransformationPlan, code: str | None = None,
             findings: list[RenderFinding] | None = None) -> CandidateRenderResult:
    finding = [RenderFinding(code=code, severity=Severity.ERROR, message="Candidate generation was blocked.")] if code else []
    plan = plan.model_copy(deep=True)
    plan.findings.extend(finding)
    for item in findings or []:
        if not any(existing.code == item.code and existing.message == item.message for existing in plan.findings):
            plan.findings.append(item)
    plan.status = PreviewStatus.BLOCKED
    report = CandidateValidationReport(source_sha256=plan.source_sha256,
        operations_planned=len(plan.operations), findings=plan.findings)
    return CandidateRenderResult(plan=plan, validation=report, semantic_diff=SemanticMigrationDiff(), status=PreviewStatus.BLOCKED)


def render_panos_candidate(
    source_path: str | Path, source_inventory: PaloAltoInventory, preview: MigrationPreview,
    target_profile: HardwareProfile, output_path: str | Path, *, allow_review: bool = False,
    force: bool = False, source_profile_id: str | None = None,
    source_panos_train: str | None = None, target_panos_train: str | None = None,
    validation_dir: str | Path | None = None, max_output_bytes: int | None = None,
    reserve_output: Callable[[int], None] | None = None,
) -> CandidateRenderResult:
    source = Path(source_path)
    output = Path(output_path)
    try:
        if source.stat().st_size > MAX_XML_BYTES:
            raise OSError("Source exceeds the 100 MiB limit")
        data = source.read_bytes()
    except OSError:
        data = b""
    plan = build_transformation_plan(data, source_inventory, preview, target_profile, allow_review=allow_review)
    registered_target = get_profile(target_profile.id)
    if registered_target is not None and registered_target.model_dump() != target_profile.model_dump():
        return _blocked(plan, "TARGET_PROFILE_CONTEXT_MISMATCH")
    if target_profile.target_render_support == TargetRenderSupport.ANALYSIS_ONLY:
        return _blocked(plan, "TARGET_PROFILE_RENDERING_NOT_VERIFIED")
    if target_profile.target_render_support == TargetRenderSupport.SCOPED:
        if not source_profile_id or not source_panos_train or not target_panos_train:
            return _blocked(plan, "SCOPED_RENDER_CONTEXT_REQUIRED")
        if registered_target is None:
            return _blocked(plan, "TARGET_PROFILE_CONTEXT_MISMATCH")
        compatibility = assess(source_inventory, source_profile_id, source_panos_train,
            target_profile.id, target_panos_train, preview.mappings)
        if compatibility.status == AssessmentStatus.BLOCKED:
            return _blocked(plan, findings=[RenderFinding(code=item.code, severity=item.severity,
                message=f"{item.source_interface or 'source'} -> {item.target_interface or 'target'}: {item.message}"
                if item.source_interface or item.target_interface else item.message)
                for item in compatibility.findings if item.severity == Severity.ERROR])
        if compatibility.status == AssessmentStatus.REVIEW_REQUIRED and not allow_review:
            return _blocked(plan, "REVIEW_APPROVAL_REQUIRED")
    if target_profile.target_render_support == TargetRenderSupport.SCOPED and (
        plan.target_render_support != TargetRenderSupport.SCOPED.value
        or any(op.operation_type == OperationType.SET_INTERFACE_LINK_SPEED or op.field == "link-duplex" for op in plan.operations)
    ):
        return _blocked(plan, "TARGET_AUTO_ONLY_LINK_SERIALIZATION_UNVERIFIED")
    if target_profile.target_render_support == TargetRenderSupport.SCOPED:
        source_ports = {item.name: item for item in source_inventory.physical_interfaces}
        target_ports = {item.name: item for item in target_profile.interfaces}
        for mapping in preview.mappings:
            port = target_ports.get(mapping.target_interface)
            if not port or port.required_condition != RequiredCondition.OPTIC_CONTEXT_LINK_FIELDS_ABSENT:
                continue
            source_port = source_ports.get(mapping.source_interface)
            settings = mapping.target_settings
            if not source_port or source_port.link_speed_explicit or source_port.link_duplex_explicit:
                return _blocked(plan, "TARGET_OPTICAL_LINK_SERIALIZATION_UNVERIFIED")
            if settings and settings.link_speed is not None:
                return _blocked(plan, "TARGET_OPTICAL_LINK_SETTING_NOT_APPLICABLE")
            if not settings or settings.optic_rate is None:
                return _blocked(plan, "TARGET_OPTIC_RATE_REQUIRED")
            if settings.optic_rate not in port.speed_capabilities:
                return _blocked(plan, "TARGET_OPTIC_RATE_UNSUPPORTED")
    if plan.status == PreviewStatus.BLOCKED:
        return _blocked(plan)
    if source.resolve() == output.resolve():
        return _blocked(plan, "OUTPUT_PATH_EQUALS_SOURCE")
    if output.exists() and not force:
        return _blocked(plan, "OUTPUT_EXISTS")
    try:
        root = _safe_tree(data)
        actual_source = parse_palo_alto_xml(source)
        if actual_source.model_dump() != source_inventory.model_dump() or sha256(source.read_bytes()).hexdigest() != plan.source_sha256:
            raise RenderFailure("SOURCE_INVENTORY_MISMATCH")
        source_root = deepcopy(root)
        resolved = []
        for op in plan.operations:
            matches = locate(root, op)
            if len(matches) != op.expected_occurrences:
                raise RenderFailure("LOCATOR_NOT_FOUND" if not matches else "LOCATOR_AMBIGUOUS")
            resolved.append((op, matches[0][0], matches[0][1]))

        unknown = unmodeled_interface_references(root, plan, resolved)
        if unknown:
            plan.findings.extend(RenderFinding(code="UNMODELED_INTERFACE_REFERENCE", severity=Severity.ERROR,
                message=f"Changed interface identity has an unmodeled XML occurrence: {location}.")
                for location in unknown)
            return _blocked(plan)

        inverse = []
        for op, node, field in resolved:
            if field == "assert":
                continue
            if field == "link-speed":
                speeds = node.findall("link-speed")
                if len(speeds) > 1 or (speeds and (speeds[0].text or "").strip() != op.source_value):
                    raise RenderFailure("OPERATION_PRECONDITION_FAILED")
                if speeds:
                    inverse.append((element_path(root, speeds[0]), "text", speeds[0].text or ""))
                    speeds[0].text = op.target_value
                else:
                    inverse.append((element_path(root, node), "delete-link-speed", ""))
                    ET.SubElement(node, "link-speed").text = op.target_value
                continue
            old = node.get("name") if field == "name" else node.text
            if old is None:
                raise RenderFailure("OPERATION_PRECONDITION_FAILED")
            inverse.append((element_path(root, node), field, old))
            if field == "name":
                node.set("name", op.target_value)
            else:
                leading = len(old) - len(old.lstrip())
                trailing = len(old) - len(old.rstrip())
                node.text = old[:leading] + op.target_value + (old[len(old)-trailing:] if trailing else "")
        for op, node, field in resolved:
            if field == "link-speed":
                speeds = node.findall("link-speed")
                if len(speeds) != 1 or (speeds[0].text or "").strip() != op.target_value:
                    raise RenderFailure("OPERATION_POSTCONDITION_FAILED")
            elif field == "assert":
                if op.operation_type == OperationType.ASSERT_AGGREGATE_MEMBERSHIP and node.get("name") != op.target_value:
                    raise RenderFailure("OPERATION_POSTCONDITION_FAILED")
                if op.operation_type == OperationType.ASSERT_SUBINTERFACE_PARENT and node.get("name") not in {
                    item.target_value for item in plan.operations if item.operation_type == OperationType.RENAME_SUBINTERFACE
                    and item.source_value == op.object_name} | {op.object_name}:
                    raise RenderFailure("OPERATION_POSTCONDITION_FAILED")
            elif (node.get("name") if field == "name" else (node.text or "").strip()) != op.target_value:
                raise RenderFailure("OPERATION_POSTCONDITION_FAILED")
        candidate_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        if max_output_bytes is not None and len(candidate_bytes) > max_output_bytes:
            raise CandidateLimitExceeded
        if reserve_output is not None:
            reserve_output(len(candidate_bytes))
        candidate_sha = sha256(candidate_bytes).hexdigest()
        try:
            with tempfile.TemporaryDirectory(dir=validation_dir) as directory:
                candidate_path = Path(directory) / "candidate.xml"
                candidate_path.write_bytes(candidate_bytes)
                candidate_inventory = parse_palo_alto_xml(candidate_path)
        except ConfigParseError as exc:
            raise RenderFailure("CANDIDATE_REPARSE_FAILED") from exc
        if candidate_inventory.model_dump() != expected_inventory(source_inventory, plan).model_dump():
            raise RenderFailure("CANDIDATE_INVENTORY_MISMATCH")
        if not preservation_audit(source_root, _safe_tree(candidate_bytes), inverse):
            raise RenderFailure("PRESERVATION_AUDIT_FAILED")
        if sha256(source.read_bytes()).hexdigest() != plan.source_sha256:
            raise RenderFailure("SOURCE_INVENTORY_MISMATCH")
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=output.parent, suffix=".tmp", delete=False) as file:
                temporary = Path(file.name)
                file.write(candidate_bytes)
            if force:
                os.replace(temporary, output)
            else:
                os.link(temporary, output)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        report = CandidateValidationReport(source_sha256=plan.source_sha256, candidate_sha256=candidate_sha,
            candidate_parse_ok=True, expected_inventory_match=True, preservation_audit_ok=True,
            operations_planned=len(plan.operations), operations_applied=len(plan.operations),
            postconditions_passed=True, valid=True)
        changes = [SemanticChange(category=op.operation_type.value, object_type=op.object_type,
            object_name=op.object_name, scope=op.scope, old_value=op.source_value,
            new_value=next((speed for speed, xml in NATIVE_QSFP_SPEED_XML.items() if xml == op.target_value), op.target_value) if op.operation_type == OperationType.SET_INTERFACE_LINK_SPEED else op.target_value)
            for op in plan.operations if op.operation_type not in
            (OperationType.ASSERT_AGGREGATE_MEMBERSHIP, OperationType.ASSERT_SUBINTERFACE_PARENT)]
        return CandidateRenderResult(plan=plan, validation=report,
            semantic_diff=SemanticMigrationDiff(changes=changes), candidate_sha256=candidate_sha,
            candidate_size_bytes=len(candidate_bytes), output_path=str(output), status=plan.status)
    except RenderFailure as exc:
        return _blocked(plan, exc.code)
    except (OSError, ValueError):
        if validation_dir is not None:
            raise
        return _blocked(plan, "OPERATION_PRECONDITION_FAILED")
