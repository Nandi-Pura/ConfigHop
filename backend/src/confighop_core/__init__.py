"""ConfigHop source inventory core."""

from .parsers.palo_alto.parser import parse_palo_alto_xml

__all__ = ["parse_palo_alto_xml"]
