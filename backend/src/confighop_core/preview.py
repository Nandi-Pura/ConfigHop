"""Count-only interface mapping preview for local PAN-OS XML exports."""

import argparse

from .errors import ConfigParseError
from .hardware import HardwareProfileError, load_hardware_profile
from .mapping import preview_interface_mappings
from .models.mapping import InterfaceMapping
from .parsers.palo_alto.parser import parse_palo_alto_xml


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview interface mapping counts without printing configuration data.")
    parser.add_argument("path", help="Local PAN-OS XML file")
    parser.add_argument("--target-profile", required=True, help="Local target hardware profile JSON")
    parser.add_argument("--map", action="append", required=True, dest="mappings", metavar="SOURCE=TARGET")
    args = parser.parse_args()
    try:
        mappings = []
        for value in args.mappings:
            source, separator, target = value.partition("=")
            if not separator or not source.strip() or not target.strip():
                raise ValueError("Invalid mapping syntax")
            mappings.append(InterfaceMapping(source_interface=source.strip(), target_interface=target.strip()))
        inventory = parse_palo_alto_xml(args.path)
        profile = load_hardware_profile(args.target_profile)
    except (ConfigParseError, HardwareProfileError, ValueError):
        parser.exit(2, "ConfigHop preview failed: invalid input or unreadable local file.\n")
    result = preview_interface_mappings(inventory, mappings, profile)
    summary = result.summary
    print("ConfigHop Interface Migration Preview")
    for label, value in (
        ("Mappings Submitted", summary.submitted_mappings),
        ("Mappings Valid", summary.valid_mappings),
        ("Derived Subinterfaces", summary.derived_subinterface_mappings),
        ("Zones", summary.zone_reference_changes),
        ("Virtual Routers", summary.virtual_router_reference_changes),
        ("Static Routes", summary.static_route_reference_changes),
        ("NAT References", summary.nat_reference_changes),
        ("Aggregate Memberships", summary.aggregate_membership_changes),
        ("Review Findings", summary.review_findings),
        ("Blocking Findings", summary.blocking_findings),
    ):
        print(f"{label}: {value}")
    print(f"Preview Status: {result.status.value}")
    return 2 if summary.blocking_findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
