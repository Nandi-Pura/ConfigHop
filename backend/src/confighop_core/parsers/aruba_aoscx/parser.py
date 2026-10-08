import re
from ipaddress import ip_interface

from ...models.switch import (LagMode, LagProtocol, StpMode, SwitchConfig, SwitchLag,
    SwitchPhysicalInterface, SwitchSvi, SwitchStaticRoute, SwitchportMode, Vlan, vlan_id)
from ..switch_common import assign, finalize, unsupported, vlan_list, warn

VENDOR = "hpe_aruba"
UNSUPPORTED = ("router ospf", "router bgp", "access-list", "ip access-list", "class ",
    "policy ", "apply policy", "vsx", "vsf", "evpn", "vxlan", "vrf ", "aaa authentication port-access",
    "port-access", "dhcpv4-snooping", "dhcp-snooping", "arp inspection", "dynamic-arp-inspection")


def parse_aruba_aoscx(text: str, config: SwitchConfig) -> SwitchConfig:
    seen: dict[tuple[str, str, str], object] = {}
    vlans: dict[int, Vlan] = {}
    ports: dict[str, SwitchPhysicalInterface] = {}
    lags: dict[int, SwitchLag] = {}
    explicit_lags: set[int] = set()
    svis: dict[int, SwitchSvi] = {}
    context: tuple[str, object] | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line == "!":
            if line == "!":
                context = None
            continue
        if not raw[0].isspace():
            context = None
            if line.startswith("hostname "):
                assign(config, seen, config, "hostname", line[9:], "SwitchConfig", "global")
            elif match := re.fullmatch(r"vlan (\d+)", line):
                try:
                    number = vlan_id(int(match[1]))
                    context = ("vlan", vlans.setdefault(number, Vlan(id=number)))
                except ValueError:
                    warn(config, "INVALID_VLAN", "Vlan", match[1], "id", "VLAN ID is outside 1-4094")
            elif line.startswith("vlan "):
                warn(config, "INVALID_VLAN", "Vlan", line[5:], "id", "VLAN ID is malformed")
            elif match := re.fullmatch(r"interface (\d+/\d+/\d+)", line):
                name = match[1]
                context = ("port", ports.setdefault(name, SwitchPhysicalInterface(name=name)))
            elif match := re.fullmatch(r"interface lag (\d+)", line):
                number = int(match[1])
                explicit_lags.add(number)
                context = ("lag", lags.setdefault(number, SwitchLag(id=number, name=f"lag {number}")))
            elif match := re.fullmatch(r"interface vlan (\d+)", line):
                try:
                    number = vlan_id(int(match[1]))
                    context = ("svi", svis.setdefault(number, SwitchSvi(vlan_id=number, name=f"vlan {number}")))
                except ValueError:
                    warn(config, "INVALID_VLAN", "SwitchSvi", match[1], "vlan_id", "SVI VLAN ID is outside 1-4094")
            elif match := re.fullmatch(r"spanning-tree mode (\S+)", line):
                mode = {"mstp": StpMode.MSTP, "rstp": StpMode.RSTP}.get(match[1], StpMode.UNKNOWN)
                assign(config, seen, config.stp, "global_mode", mode, "SwitchStp", "global")
                if mode == StpMode.UNKNOWN:
                    unsupported(config, VENDOR, "global", None, "STP mode", line)
            elif line.startswith("ip route "):
                parts = line.split()
                try:
                    if len(parts) < 4:
                        raise ValueError("incomplete route")
                    config.static_routes.append(SwitchStaticRoute(destination=parts[2], next_hop=parts[3]))
                except ValueError:
                    warn(config, "INVALID_ROUTE", "SwitchStaticRoute", None, "destination", "Static route could not be normalized")
            elif line.lower().startswith(UNSUPPORTED):
                unsupported(config, VENDOR, "global", None, line.split()[0], line)
            continue
        if context is None:
            if line.lower().startswith(UNSUPPORTED):
                unsupported(config, VENDOR, "global", None, line.split()[0], line)
            continue
        kind, obj = context
        name = getattr(obj, "name", "global")
        if line.lower().startswith(UNSUPPORTED):
            unsupported(config, VENDOR, kind, name, line.split()[0], line)
        elif kind == "vlan":
            if line.startswith("name "):
                assign(config, seen, obj, "name", line[5:], "Vlan", str(obj.id))
        elif line.startswith("description "):
            assign(config, seen, obj, "description", line[12:], kind, name)
        elif line in {"shutdown", "no shutdown"}:
            assign(config, seen, obj, "admin_enabled", line == "no shutdown", kind, name)
        elif kind in {"port", "lag"}:
            if line == "no routing":
                pass
            elif line == "routing":
                assign(config, seen, obj, "switchport_mode", SwitchportMode.ROUTED, kind, name)
            elif match := re.fullmatch(r"vlan access (\d+)", line):
                try:
                    assign(config, seen, obj, "access_vlan", vlan_id(int(match[1])), kind, name)
                    assign(config, seen, obj, "switchport_mode", SwitchportMode.ACCESS, kind, name)
                except ValueError:
                    warn(config, "INVALID_VLAN", kind, name, "access_vlan", "VLAN ID is outside 1-4094")
            elif line.startswith("vlan access "):
                warn(config, "INVALID_VLAN", kind, name, "access_vlan", "VLAN ID is malformed")
            elif match := re.fullmatch(r"vlan trunk native (\d+)", line):
                try:
                    assign(config, seen, obj, "native_vlan", vlan_id(int(match[1])), kind, name)
                    assign(config, seen, obj, "switchport_mode", SwitchportMode.TRUNK, kind, name)
                except ValueError:
                    warn(config, "INVALID_VLAN", kind, name, "native_vlan", "VLAN ID is outside 1-4094")
            elif line.startswith("vlan trunk native "):
                warn(config, "INVALID_VLAN", kind, name, "native_vlan", "VLAN ID is malformed")
            elif line.startswith("vlan trunk allowed "):
                try:
                    assign(config, seen, obj, "allowed_vlans", vlan_list(line[19:]), kind, name)
                    assign(config, seen, obj, "switchport_mode", SwitchportMode.TRUNK, kind, name)
                except ValueError:
                    warn(config, "INVALID_VLAN_LIST", kind, name, "allowed_vlans", "Malformed or out-of-range VLAN list")
            elif kind == "port" and (match := re.fullmatch(r"lag (\d+)", line)):
                number = int(match[1])
                assign(config, seen, obj, "lag_id", number, kind, name)
                if obj.lag_id == number:
                    lags.setdefault(number, SwitchLag(id=number, name=f"lag {number}"))
            elif kind == "lag" and (match := re.fullmatch(r"lacp mode (active|passive)", line)):
                assign(config, seen, obj, "mode", LagMode(match[1].upper()), kind, name)
                assign(config, seen, obj, "protocol", LagProtocol.LACP, kind, name)
            elif line == "spanning-tree port-type admin-edge":
                if kind == "port":
                    obj.stp_edge = True
                config.stp.edge_interfaces.append(name)
        if kind in {"port", "lag", "svi"} and line.startswith("ip address "):
            try:
                address = str(ip_interface(line[11:]))
                if address not in obj.ip_addresses:
                    obj.ip_addresses.append(address)
            except ValueError:
                warn(config, "INVALID_IP_ADDRESS", kind, name, "ip_addresses", "IP address could not be normalized")
    config.vlans = list(vlans.values())
    config.physical_interfaces = list(ports.values())
    config.lags = list(lags.values())
    config.svis = list(svis.values())
    for number in sorted(set(lags) - explicit_lags):
        warn(config, "MISSING_LAG_BLOCK", "SwitchLag", lags[number].name, "id", "Member references a LAG without a logical interface block")
    return finalize(config)
