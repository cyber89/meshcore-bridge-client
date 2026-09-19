from datetime import datetime

from pydantic import BaseModel, Field


class UserCreateRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=255)
    role: str = Field(min_length=1, max_length=32)
    display_name: str | None = Field(default=None, max_length=128)
    is_active: bool = True


class UserUpdateRequest(BaseModel):
    role: str | None = Field(default=None, min_length=1, max_length=32)
    display_name: str | None = Field(default=None, max_length=128)
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=1, max_length=255)


class UserManagementResponse(BaseModel):
    id: str
    email: str
    role: str
    display_name: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
