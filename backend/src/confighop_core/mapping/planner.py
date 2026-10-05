from collections import Counter, defaultdict

from ..dependencies import build_dependency_index
from ..models.dependency import ReferenceType
from ..models.hardware import HardwareProfile
from ..models.inventory import PaloAltoInventory
from ..models.mapping import (
    ChangeAction, CoverageStatus, DependencyCoverage, DerivedSubinterfaceMapping,
    InterfaceMapping, InterfaceMigrationImpact, MappingStatus, MigrationFinding,
    MigrationPreview, MigrationSummary, PreviewStatus, ReferenceChange, Severity,
)
from .validator import validate_mappings


_GAPS = {
    "layer2": "Layer2 bridge/VLAN dependencies are not fully represented in Core v0.2.",
    "virtual_wire": "Full virtual-wire membership dependencies are not represented in Core v0.2.",
    "aggregate_member": "Aggregate member hardware compatibility is not verified in Core v0.2.",
}


def preview_interface_mappings(
    inventory: PaloAltoInventory, mappings: list[InterfaceMapping], target_profile: HardwareProfile,
) -> MigrationPreview:
    findings = validate_mappings(inventory, mappings, target_profile)
    errors = {(finding.source_interface, finding.target_interface) for finding in findings if finding.severity == Severity.ERROR}
    global_error = any(finding.code == "MULTI_DEVICE_INVENTORY_UNSUPPORTED" for finding in findings)
    physical = {interface.name: interface for interface in inventory.physical_interfaces}
    children = defaultdict(list)
    for child in inventory.subinterfaces:
        children[child.parent_interface].append(child)
    index = build_dependency_index(inventory)
    impacts = []
    for mapping in mappings:
        local_findings = [finding for finding in findings if finding.source_interface == mapping.source_interface
            and finding.target_interface == mapping.target_interface]
        invalid = global_error or (mapping.source_interface, mapping.target_interface) in errors
        source = physical.get(mapping.source_interface)
        gaps = []
        if not invalid and source:
            if source.mode in _GAPS:
                gaps.append(_GAPS[source.mode])
                local_findings.append(MigrationFinding(code="PARTIAL_DEPENDENCY_COVERAGE", severity=Severity.WARNING,
                    source_interface=mapping.source_interface, target_interface=mapping.target_interface,
                    message="Dependency coverage is partial for this interface mode."))
            if source.aggregate_group:
                if _GAPS["aggregate_member"] not in gaps:
                    gaps.append(_GAPS["aggregate_member"])
                local_findings.append(MigrationFinding(code="AGGREGATE_MEMBER_REVIEW", severity=Severity.WARNING,
                    source_interface=mapping.source_interface, target_interface=mapping.target_interface,
                    message="Aggregate member compatibility requires engineer review."))
        coverage = DependencyCoverage(status=CoverageStatus.PARTIAL if gaps else CoverageStatus.SUPPORTED,
            covered_reference_types=list(ReferenceType), known_gaps=gaps)
        derived = []
        changes = []
        if not invalid:
            identities = {mapping.source_interface: mapping.target_interface}
            for child in children[mapping.source_interface]:
                prefix = f"{child.parent_interface}."
                if not child.name.startswith(prefix):
                    local_findings.append(MigrationFinding(code="PARTIAL_DEPENDENCY_COVERAGE", severity=Severity.WARNING,
                        source_interface=mapping.source_interface, target_interface=mapping.target_interface,
                        message="A child interface name cannot be derived from its parent identity."))
                    continue
                suffix = child.name[len(prefix):]
                target_name = f"{mapping.target_interface}.{suffix}"
                derived.append(DerivedSubinterfaceMapping(source_interface=child.name, target_interface=target_name,
                    source_parent=child.parent_interface, target_parent=mapping.target_interface,
                    unit_suffix=suffix, tag=child.tag))
                identities[child.name] = target_name
            for old, new in identities.items():
                for ref in index.get(old, []):
                    changes.append(ReferenceChange(reference_type=ref.reference_type,
                        object_type=ref.object_type, object_name=ref.object_name, scope=ref.scope,
                        field=ref.field, old_value=old, new_value=new,
                        action=ChangeAction.PRESERVE if old == new else ChangeAction.UPDATE_REFERENCE,
                        status=MappingStatus.REVIEW if gaps else MappingStatus.MAPPED))
        findings.extend(finding for finding in local_findings if finding not in findings)
        impacts.append(InterfaceMigrationImpact(source_interface=mapping.source_interface,
            target_interface=mapping.target_interface,
            mapping_status=MappingStatus.CONFLICT if invalid else MappingStatus.REVIEW if local_findings else MappingStatus.MAPPED,
            derived_subinterfaces=derived, reference_changes=changes, findings=local_findings, coverage=coverage))
    counts = Counter(change.reference_type for impact in impacts for change in impact.reference_changes
        if change.action == ChangeAction.UPDATE_REFERENCE)
    summary = MigrationSummary(submitted_mappings=len(mappings),
        valid_mappings=sum(impact.mapping_status in (MappingStatus.MAPPED, MappingStatus.REVIEW) for impact in impacts),
        derived_subinterface_mappings=sum(len(impact.derived_subinterfaces) for impact in impacts),
        zone_reference_changes=counts[ReferenceType.ZONE_INTERFACE],
        virtual_router_reference_changes=counts[ReferenceType.VIRTUAL_ROUTER_INTERFACE],
        static_route_reference_changes=counts[ReferenceType.STATIC_ROUTE_EGRESS_INTERFACE],
        nat_reference_changes=counts[ReferenceType.NAT_INTERFACE_REFERENCE],
        aggregate_membership_changes=counts[ReferenceType.AGGREGATE_MEMBERSHIP],
        review_findings=sum(finding.severity == Severity.WARNING for finding in findings),
        blocking_findings=sum(finding.severity == Severity.ERROR for finding in findings))
    status = (PreviewStatus.BLOCKED if summary.blocking_findings else
        PreviewStatus.REVIEW_REQUIRED if summary.review_findings else PreviewStatus.READY)
    gaps = list(dict.fromkeys(gap for impact in impacts for gap in impact.coverage.known_gaps))
    coverage = DependencyCoverage(status=CoverageStatus.PARTIAL if gaps else CoverageStatus.SUPPORTED,
        covered_reference_types=list(ReferenceType), known_gaps=gaps)
    return MigrationPreview(mappings=mappings, impacts=impacts, findings=findings,
        summary=summary, status=status, coverage=coverage)
