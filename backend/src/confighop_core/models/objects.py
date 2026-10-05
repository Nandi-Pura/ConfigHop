from pydantic import BaseModel

from .common import ObjectScope


class AddressObject(BaseModel):
    name: str
    scope: ObjectScope
    kind: str
    value: str | None = None
    description: str | None = None


class ServiceObject(BaseModel):
    name: str
    scope: ObjectScope
    protocol: str
    destination_port: str | None = None
    source_port: str | None = None
    description: str | None = None
