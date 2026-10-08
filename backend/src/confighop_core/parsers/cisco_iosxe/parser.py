import re
from ipaddress import ip_address, ip_interface, ip_network

from ...models.switch import (LagMode, LagProtocol, StpMode, SwitchConfig, SwitchLag,
    SwitchPhysicalInterface, SwitchSvi, SwitchStaticRoute, SwitchportMode, Vlan, vlan_id)
from ..switch_common import assign, finalize, unsupported, vlan_list, warn

VENDOR = "cisco"
UNSUPPORTED = ("router ospf", "router bgp", "ip access-list", "ipv6 access-list", "policy-map",
    "class-map", "service-policy", "vrf definition", "switch virtual", "stackwise",
    "authentication ", "dot1x ", "ip dhcp snooping", "ip arp inspection", "private-vlan",
    "switchport private-vlan")
PORT = re.compile(r"(?:GigabitEthernet|TenGigabitEthernet|TwentyFiveGigE|FortyGigabitEthernet)\d.*")


def parse_cisco_iosxe(text: str, config: SwitchConfig) -> SwitchConfig:
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
            elif line.startswith("interface "):
                name = line[10:]
                if PORT.fullmatch(name):
                    context = ("port", ports.setdefault(name, SwitchPhysicalInterface(name=name)))
                elif match := re.fullmatch(r"Port-channel(\d+)", name):
                    number = int(match[1])
                    explicit_lags.add(number)
                    context = ("lag", lags.setdefault(number, SwitchLag(id=number, name=name)))
                elif match := re.fullmatch(r"Vlan(\d+)", name):
                    try:
                        number = vlan_id(int(match[1]))
                        context = ("svi", svis.setdefault(number, SwitchSvi(vlan_id=number, name=name)))
                    except ValueError:
                        warn(config, "INVALID_VLAN", "SwitchSvi", name, "vlan_id", "SVI VLAN ID is outside 1-4094")
                else:
                    unsupported(config, VENDOR, "interface", name, "interface type", line)
            elif match := re.fullmatch(r"spanning-tree mode (\S+)", line):
                mode = {"pvst": StpMode.PVST, "rapid-pvst": StpMode.RAPID_PVST, "mst": StpMode.MSTP}.get(match[1], StpMode.UNKNOWN)
                assign(config, seen, config.stp, "global_mode", mode, "SwitchStp", "global")
                if mode == StpMode.UNKNOWN:
                    unsupported(config, VENDOR, "global", None, "STP mode", line)
            elif line.startswith("ip route "):
                parts = line.split()
                try:
                    if len(parts) < 5:
                        raise ValueError("incomplete route")
                    destination = str(ip_network(f"{parts[2]}/{parts[3]}", strict=False))
                    try:
                        next_hop = str(ip_address(parts[4]))
                        egress = None
                        remaining = parts[5:]
                    except ValueError:
                        egress = parts[4]
                        next_hop = str(ip_address(parts[5])) if len(parts) > 5 else None
                        remaining = parts[6:]
                    config.static_routes.append(SwitchStaticRoute(destination=destination, next_hop=next_hop,
                        egress_interface=egress, metric=int(remaining[0]) if remaining and remaining[0].isdigit() else None))
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
            if line == "no switchport":
                assign(config, seen, obj, "switchport_mode", SwitchportMode.ROUTED, kind, name)
            elif line == "switchport":
                assign(config, seen, obj, "switchport_mode", SwitchportMode.UNKNOWN, kind, name)
            elif match := re.fullmatch(r"switchport mode (access|trunk)", line):
                assign(config, seen, obj, "switchport_mode", SwitchportMode(match[1].upper()), kind, name)
            elif match := re.fullmatch(r"switchport (access|voice) vlan (\d+)", line):
                try:
                    number = vlan_id(int(match[2]))
                    if match[1] == "voice" and kind != "port":
                        unsupported(config, VENDOR, kind, name, "voice VLAN on LAG", line)
                    else:
                        assign(config, seen, obj, f"{match[1]}_vlan", number, kind, name)
                except ValueError:
                    warn(config, "INVALID_VLAN", kind, name, match[1], "VLAN ID is outside 1-4094")
            elif line.startswith(("switchport access vlan ", "switchport voice vlan ")):
                warn(config, "INVALID_VLAN", kind, name, "vlan", "VLAN ID is malformed")
            elif match := re.fullmatch(r"switchport trunk native vlan (\d+)", line):
                try:
                    assign(config, seen, obj, "native_vlan", vlan_id(int(match[1])), kind, name)
                except ValueError:
                    warn(config, "INVALID_VLAN", kind, name, "native_vlan", "VLAN ID is outside 1-4094")
            elif line.startswith("switchport trunk native vlan "):
                warn(config, "INVALID_VLAN", kind, name, "native_vlan", "VLAN ID is malformed")
            elif line.startswith("switchport trunk allowed vlan "):
                try:
                    assign(config, seen, obj, "allowed_vlans", vlan_list(line[30:]), kind, name)
                except ValueError:
                    warn(config, "INVALID_VLAN_LIST", kind, name, "allowed_vlans", "Malformed or out-of-range VLAN list")
            elif kind == "port" and (match := re.fullmatch(r"channel-group (\d+) mode (active|passive|on)", line)):
                number, mode = int(match[1]), LagMode(match[2].upper())
                assign(config, seen, obj, "lag_id", number, kind, name)
                if obj.lag_id != number:
                    continue
                lag = lags.setdefault(number, SwitchLag(id=number, name=f"Port-channel{number}"))
                assign(config, seen, lag, "mode", mode, "lag", lag.name)
                assign(config, seen, lag, "protocol", LagProtocol.STATIC if mode == LagMode.ON else LagProtocol.LACP, "lag", lag.name)
            elif kind == "port" and line == "spanning-tree portfast":
                obj.stp_edge = True
                config.stp.edge_interfaces.append(name)
        if kind in {"port", "lag", "svi"} and line.startswith("ip address "):
            parts = line.split()
            try:
                address = str(ip_interface(f"{parts[2]}/{parts[3]}"))
                if address not in obj.ip_addresses:
                    obj.ip_addresses.append(address)
            except (IndexError, ValueError):
                warn(config, "INVALID_IP_ADDRESS", kind, name, "ip_addresses", "IP address could not be normalized")
    config.vlans = list(vlans.values())
    config.physical_interfaces = list(ports.values())
    config.lags = list(lags.values())
    config.svis = list(svis.values())
    for number in sorted(set(lags) - explicit_lags):
        warn(config, "MISSING_LAG_BLOCK", "SwitchLag", lags[number].name, "id", "Member references a LAG without a logical interface block")
    return finalize(config)
