"""Pydantic models for service layer."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ProjectInfo(BaseModel):
    """Project information model."""

    name: str
    spider_count: int
    last_crawled_at: datetime | None = None


class InspectionResult(BaseModel):
    """URL inspection result model."""

    url: str
    status_code: int | None = None
    detected_selectors: list[str] | None = None
    js_rendered: bool | None = None
    cloudflare_protected: bool | None = None
    url_params: dict[str, str] | None = None
    output_dir: str | None = None
    html_snapshot: str | None = None
    title: str | None = None
    description: str | None = None
    links: list[str] | None = None
    headers: dict[str, str] | None = None
    inspected_at: datetime | None = None
