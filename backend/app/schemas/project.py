"""Pydantic schemas for the Project resource."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    domain: str = Field(min_length=1, max_length=255)
    base_url: HttpUrl
    robots_respect: bool = True
    js_render: bool = False
    # ``None``: keine Auto-Crawls. Sonst Intervall in Minuten — z.B. 60
    # für stündlich, 1440 für täglich, 10080 für wöchentlich.
    schedule_interval_minutes: int | None = Field(default=None, ge=15, le=525_600)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    base_url: HttpUrl | None = None
    robots_respect: bool | None = None
    js_render: bool | None = None
    # ``Field`` with default=... lets PATCH distinguish "leave unchanged"
    # (omitted from request body) from "clear the schedule" (explicit null).
    # Pydantic v2 model_dump(exclude_unset=True) handles that for us.
    schedule_interval_minutes: int | None = Field(default=None, ge=15, le=525_600)


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    domain: str
    base_url: str
    robots_respect: bool
    js_render: bool
    schedule_interval_minutes: int | None
    next_scheduled_at: datetime | None
    created_at: datetime
    updated_at: datetime
