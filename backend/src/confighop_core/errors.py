class ConfigParseError(Exception):
    """A configuration could not be safely converted into inventory."""


class UnsupportedConfigFormatError(ConfigParseError):
    """The document is not a supported Palo Alto config export."""


class ConfigTooLargeError(ConfigParseError):
    """The input exceeds the parser's size limit."""


class MalformedXmlError(ConfigParseError):
    """The XML is malformed or contains unsafe XML constructs."""
