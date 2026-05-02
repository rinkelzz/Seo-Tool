"""Pydantic schemas for the Project resource."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    domain: str = Field(min_length=1, max_length=255)
    base_url: HttpUrl
    robots_respect: bool = True
    js_render: bool = False


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    base_url: HttpUrl | None = None
    robots_respect: bool | None = None
    js_render: bool | None = None


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    domain: str
    base_url: str
    robots_respect: bool
    js_render: bool
    created_at: datetime
    updated_at: datetime
