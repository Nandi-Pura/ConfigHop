from pydantic import BaseModel, Field


class VirtualRouter(BaseModel):
    name: str
    interface_members: list[str] = Field(default_factory=list)
    static_route_names: list[str] = Field(default_factory=list)


class StaticRoute(BaseModel):
    name: str
    virtual_router: str
    destination: str | None = None
    egress_interface: str | None = None
    metric: int | None = None
    next_hop_type: str | None = None
    next_hop_value: str | None = None
    bfd_profile: str | None = None
