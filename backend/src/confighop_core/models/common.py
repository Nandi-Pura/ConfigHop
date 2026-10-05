from typing import Literal

from pydantic import BaseModel


class ObjectScope(BaseModel):
    type: Literal["shared", "vsys"]
    name: str | None = None


class ParserWarning(BaseModel):
    code: str
    object_type: str
    object_name: str | None = None
    field: str
    message: str
