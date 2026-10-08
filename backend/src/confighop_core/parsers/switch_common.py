import re

from ..models.common import ParserWarning
from ..models.switch import SwitchConfig, SwitchLag, SwitchportMode, VendorExtension, vlan_id


def vlan_list(value: str) -> list[int]:
    result: set[int] = set()
    for part in value.split(","):
        if re.fullmatch(r"\d+", part):
            result.add(vlan_id(int(part)))
        elif match := re.fullmatch(r"(\d+)-(\d+)", part):
            start, end = map(int, match.groups())
            vlan_id(start)
            vlan_id(end)
            if start > end:
                raise ValueError("descending VLAN range")
            result.update(range(start, end + 1))
        else:
            raise ValueError("malformed VLAN list")
    return sorted(result)


def warn(config: SwitchConfig, code: str, kind: str, name: str | None, field: str, message: str) -> None:
    config.parser_warnings.append(ParserWarning(code=code, object_type=kind, object_name=name, field=field, message=message))


def unsupported(config: SwitchConfig, vendor: str, scope: str, name: str | None, feature: str, command: str) -> None:
    warn(config, "UNSUPPORTED_FEATURE", scope, name, feature, f"{feature} is detected but not normalized")
    config.vendor_extensions.append(VendorExtension(vendor=vendor, scope=scope, object_name=name,
        feature=feature, raw_value=command, reason="No canonical normalization in this foundation"))


def assign(config: SwitchConfig, seen: dict[tuple[str, str, str], object], obj: object,
           field: str, value: object, kind: str, name: str) -> None:
    key = (kind, name, field)
    if key in seen and seen[key] != value:
        warn(config, "CONFLICTING_DECLARATION", kind, name, field, "Conflicting declarations; first value retained")
        return
    seen[key] = value
    setattr(obj, field, value)


def finalize(config: SwitchConfig) -> SwitchConfig:
    defined = {vlan.id for vlan in config.vlans}
    for item in [*config.physical_interfaces, *config.lags]:
        refs = [item.access_vlan, item.native_vlan, *item.allowed_vlans]
        if hasattr(item, "voice_vlan"):
            refs.append(item.voice_vlan)
        for number in sorted({number for number in refs if number is not None} - defined):
            warn(config, "UNDEFINED_VLAN", type(item).__name__, item.name, "vlan", f"VLAN {number} is referenced but not defined")
    for svi in config.svis:
        if svi.vlan_id not in defined:
            warn(config, "UNDEFINED_VLAN", "SwitchSvi", svi.name, "vlan_id", f"VLAN {svi.vlan_id} is referenced but not defined")
    lags = {lag.id: lag for lag in config.lags}
    for port in config.physical_interfaces:
        if port.lag_id is not None:
            if port.lag_id not in lags:
                lags[port.lag_id] = SwitchLag(id=port.lag_id, name=f"lag {port.lag_id}")
                config.lags.append(lags[port.lag_id])
                warn(config, "MISSING_LAG_BLOCK", "SwitchLag", lags[port.lag_id].name, "id", "Member references a LAG without a logical interface block")
            lags[port.lag_id].members.append(port.name)
        if port.switchport_mode == SwitchportMode.ROUTED and (port.access_vlan or port.native_vlan or port.allowed_vlans):
            warn(config, "ROUTED_SWITCHPORT_CONFLICT", "SwitchPhysicalInterface", port.name, "switchport_mode", "Routed interface also has switchport VLAN settings")
        if port.switchport_mode in {SwitchportMode.ACCESS, SwitchportMode.TRUNK} and port.ip_addresses:
            warn(config, "SWITCHPORT_IP_CONFLICT", "SwitchPhysicalInterface", port.name, "ip_addresses", "Layer 2 switchport also has an IP address")
    return SwitchConfig.model_validate(config.model_dump())
