from pydantic import BaseModel, Field


class EstateObject(BaseModel):
    id: str
    kind: str
    name: str
    owner: str = ""
    size_bytes: int = 0
    item_count: int = 0
    last_modified: str = ""
    flags: list[str] = Field(default_factory=list)
    sha256: str | None = None


class Estate(BaseModel):
    tenant_id: str
    captured_at: str
    objects: list[EstateObject] = Field(default_factory=list)
