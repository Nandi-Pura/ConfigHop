from pydantic import BaseModel


class PlatformMetadata(BaseModel):
    vendor: str = "palo_alto"
    config_version: str | None = None
    detail_version: str | None = None
    source_format: str = "panos_xml"


class DeviceEntry(BaseModel):
    name: str
