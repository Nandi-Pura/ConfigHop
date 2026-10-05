from pydantic import BaseModel, Field


class SecurityRule(BaseModel):
    name: str
    uuid: str | None = None
    vsys: str
    from_zones: list[str] = Field(default_factory=list)
    to_zones: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    destinations: list[str] = Field(default_factory=list)
    applications: list[str] = Field(default_factory=list)
    services: list[str] = Field(default_factory=list)
    action: str | None = None
    disabled: bool | None = None
    description: str | None = None


class NatRule(BaseModel):
    name: str
    uuid: str | None = None
    vsys: str
    from_zones: list[str] = Field(default_factory=list)
    to_zones: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    destinations: list[str] = Field(default_factory=list)
    service: str | None = None
    source_translation_type: str | None = None
    destination_translation_type: str | None = None
    interface_references: list[str] = Field(default_factory=list)
    disabled: bool | None = None
