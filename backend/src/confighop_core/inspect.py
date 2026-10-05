"""Print a safe count-only inventory summary for a local PAN-OS XML export."""

import argparse

from .errors import ConfigParseError
from .parsers.palo_alto.parser import parse_palo_alto_xml


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect a local Palo Alto XML configuration without printing its contents.")
    parser.add_argument("path", help="Path to a local PAN-OS XML configuration")
    args = parser.parse_args()
    try:
        inventory = parse_palo_alto_xml(args.path)
    except ConfigParseError as exc:
        parser.exit(2, f"ConfigHop inspection failed: {exc}\n")

    counts = (
        ("Physical Ethernet", inventory.physical_interfaces),
        ("Subinterfaces", inventory.subinterfaces),
        ("Aggregate Ethernet", inventory.aggregate_interfaces),
        ("VLAN Interfaces", inventory.vlan_interfaces),
        ("Loopbacks", inventory.loopback_interfaces),
        ("VSYS", inventory.vsys_names),
        ("Zones", inventory.zones),
        ("Virtual Routers", inventory.virtual_routers),
        ("Static Routes", inventory.static_routes),
        ("Address Objects", inventory.address_objects),
        ("Service Objects", inventory.service_objects),
        ("Security Rules", inventory.security_rules),
        ("NAT Rules", inventory.nat_rules),
        ("Warnings", inventory.warnings),
    )
    print("ConfigHop Palo Alto Inventory")
    print("Vendor: Palo Alto Networks")
    print(f"Config Version: {inventory.platform.config_version or 'unknown'}")
    print(f"Detail Version: {inventory.platform.detail_version or 'unknown'}")
    for label, values in counts:
        print(f"{label}: {len(values)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
