import ipaddress
from xml.etree.ElementTree import Element

from confighop_core.models.common import ParserWarning


def text(entry: Element, path: str) -> str | None:
    value = entry.findtext(path)
    return value.strip() if value and value.strip() else None


def members(entry: Element, path: str) -> list[str]:
    return [member.text.strip() for member in entry.findall(path) if member.text and member.text.strip()]


def interface_mode(entry: Element) -> str:
    for tag, mode in (("layer3", "layer3"), ("layer2", "layer2"), ("virtual-wire", "virtual_wire")):
        if entry.find(tag) is not None:
            return mode
    return "aggregate_member" if entry.find("aggregate-group") is not None else "unknown"


def ip_addresses(entry: Element, path: str, object_type: str, name: str, warnings: list[ParserWarning]) -> list[str]:
    result = []
    for address in entry.findall(path):
        value = address.get("name") or (address.text.strip() if address.text else None)
        if not value:
            continue
        result.append(value)
        try:
            ipaddress.ip_interface(value)
        except ValueError:
            warnings.append(ParserWarning(code="INVALID_IP_VALUE", object_type=object_type, object_name=name, field="ip_addresses", message="IP address is not a valid interface address; original text was preserved."))
    return result


def optional_bool(entry: Element, path: str) -> bool | None:
    value = text(entry, path)
    if value is None:
        return None
    if value.lower() in ("yes", "true", "1"):
        return True
    if value.lower() in ("no", "false", "0"):
        return False
    return None


def optional_int(entry: Element, path: str, object_type: str, name: str, warnings: list[ParserWarning]) -> int | None:
    value = text(entry, path)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        warnings.append(ParserWarning(code="MALFORMED_OBJECT", object_type=object_type, object_name=name, field=path, message="Expected an integer; field was omitted."))
        return None


def child_tag(entry: Element, path: str) -> str | None:
    parent = entry.find(path)
    return next((child.tag for child in parent), None) if parent is not None else None
