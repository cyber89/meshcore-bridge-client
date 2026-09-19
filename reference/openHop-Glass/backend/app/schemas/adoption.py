from pydantic import BaseModel, Field


class AdoptionActionRequest(BaseModel):
    note: str | None = Field(default=None, max_length=512)


class AdoptionActionResponse(BaseModel):
    repeater_id: str
    node_name: str
    status: str

