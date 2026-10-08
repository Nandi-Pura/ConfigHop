from .errors import ConfigTooLargeError
from .hardware.switch import get_switch_profile, switch_version_support
from .models.hardware import SoftwareFamily
from .models.switch import SwitchConfig, SwitchPlatform
from .parsers.aruba_aoscx import parse_aruba_aoscx
from .parsers.cisco_iosxe import parse_cisco_iosxe
from .parsers.switch_common import warn

MAX_SWITCH_TEXT_BYTES = 100 * 1024 * 1024


def inspect_switch_config(text: str, vendor: str, software_family: SoftwareFamily,
                          software_version: str, hardware_profile_id: str) -> SwitchConfig:
    if len(text) > MAX_SWITCH_TEXT_BYTES or len(text.encode("utf-8")) > MAX_SWITCH_TEXT_BYTES:
        raise ConfigTooLargeError("Switch configuration exceeds 100 MiB")
    profile = get_switch_profile(hardware_profile_id)
    if profile is None or profile.vendor != vendor or profile.software_family != software_family:
        raise ValueError("Selected Switch vendor, software family, and hardware profile do not match")
    if switch_version_support(hardware_profile_id, software_version) != "SUPPORTED":
        raise ValueError("VERSION_NOT_VERIFIED")
    config = SwitchConfig(platform=SwitchPlatform(vendor=vendor, software_family=software_family,
        software_version=software_version, hardware_profile_id=hardware_profile_id))
    parser = parse_cisco_iosxe if software_family == SoftwareFamily.IOS_XE else parse_aruba_aoscx
    config = parser(text, config)
    known = {item.name for item in profile.interfaces}
    for port in config.physical_interfaces:
        if port.name not in known:
            warn(config, "HARDWARE_PORT_NOT_VERIFIED", "SwitchPhysicalInterface", port.name, "name",
                "Port is absent from the exact hardware profile; modular uplink or other hardware context is unknown")
    return SwitchConfig.model_validate(config.model_dump())
