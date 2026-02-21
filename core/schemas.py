from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional, Dict, Any
from datetime import datetime, timezone


class ScrapedArticle(BaseModel):
    """Standardized model for scraped article data."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    url: str
    title: str
    content: str
    author: Optional[str] = None
    published_date: Optional[datetime] = None
    source: str
    extracted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Optional[Dict[str, Any]] = {}
    html: Optional[str] = None

    @field_validator('content')
    @classmethod
    def content_must_be_long_enough(cls, v):
        if not v or len(v.strip()) < 100:
            raise ValueError('Content too short (< 100 chars)')
        return v

    @field_validator('title')
    @classmethod
    def title_must_exist(cls, v):
        if not v or len(v.strip()) < 5:
            raise ValueError('Title too short or missing')
        return v
