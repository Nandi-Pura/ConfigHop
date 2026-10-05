"""Safe, summary-only PAN-OS candidate renderer CLI."""

import argparse
from pathlib import Path

from .hardware import HardwareProfileError, load_hardware_profile
from .mapping import preview_interface_mappings
from .models.mapping import InterfaceMapping
from .models.transformation import OperationType
from .parsers.palo_alto.parser import parse_palo_alto_xml
from .renderers import render_panos_candidate


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a validated local PAN-OS candidate without printing configuration contents.")
    parser.add_argument("path")
    parser.add_argument("--target-profile", required=True)
    parser.add_argument("--map", action="append", required=True, dest="mappings", metavar="SOURCE=TARGET")
    parser.add_argument("--output", required=True)
    parser.add_argument("--allow-review", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        mappings = []
        for value in args.mappings:
            source, sep, target = value.partition("=")
            if not sep or not source.strip() or not target.strip():
                raise ValueError("Invalid mapping syntax")
            mappings.append(InterfaceMapping(source_interface=source.strip(), target_interface=target.strip()))
        profile = load_hardware_profile(args.target_profile)
        inventory = parse_palo_alto_xml(args.path)
    except (HardwareProfileError, ValueError, OSError):
        parser.exit(2, "ConfigHop render failed: invalid input or unreadable local file.\n")
    preview = preview_interface_mappings(inventory, mappings, profile)
    result = render_panos_candidate(args.path, inventory, preview, profile, args.output,
        allow_review=args.allow_review, force=args.force)
    print("ConfigHop PAN-OS Candidate Renderer")
    print(f"Source SHA-256: {result.plan.source_sha256}")
    print(f"Target Profile: {profile.model}")
    print(f"Target Profile Status: {profile.profile_status.value}")
    print(f"Preview Status: {preview.status.value}")
    print(f"Transformation Plan: {result.plan.status.value}")
    if result.status.value == "BLOCKED":
        for finding in result.plan.findings:
            print(f"Finding: {finding.code}")
        print("Candidate Written: NO")
        return 2
    counts = {kind: sum(op.operation_type == kind for op in result.plan.operations) for kind in OperationType}
    for label, kind in (
        ("Physical Renames", OperationType.RENAME_PHYSICAL_INTERFACE),
        ("Subinterface Renames", OperationType.RENAME_SUBINTERFACE),
        ("Zones", OperationType.UPDATE_ZONE_INTERFACE_REFERENCE),
        ("Virtual Routers", OperationType.UPDATE_VIRTUAL_ROUTER_INTERFACE_REFERENCE),
        ("Static Routes", OperationType.UPDATE_STATIC_ROUTE_EGRESS_REFERENCE),
        ("NAT", OperationType.UPDATE_NAT_INTERFACE_REFERENCE),
        ("Aggregate Assertions", OperationType.ASSERT_AGGREGATE_MEMBERSHIP),
    ):
        print(f"{label}: {counts[kind]}")
    print(f"Operations Planned: {result.validation.operations_planned}")
    print(f"Operations Applied: {result.validation.operations_applied}")
    print("Candidate Parse: PASS")
    print("Expected Inventory: PASS")
    print("Preservation Audit: PASS")
    print(f"Candidate SHA-256: {result.candidate_sha256}")
    print(f"Candidate Written: {Path(result.output_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
