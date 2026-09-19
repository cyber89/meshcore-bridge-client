from pydantic import BaseModel, Field


class BootstrapStatusResponse(BaseModel):
    needs_bootstrap: bool
    server_setup_complete: bool


class BootstrapAdminRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=255)
    display_name: str | None = Field(default=None, max_length=128)


class BootstrapAdminResponse(BaseModel):
    user_id: str
    email: str
    role: str

