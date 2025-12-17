from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from datetime import datetime

class ScrapedArticle(BaseModel):
    """
    Standardized model for scraped article data.
    Ensures consistent output across different extractors.
    """
    url: str
    title: str
    content: str
    author: Optional[str] = None
    published_date: Optional[datetime] = None
    source: str
    extracted_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Optional[Dict[str, Any]] = {}

    @validator('content')
    def content_must_be_long_enough(cls, v):
        if not v or len(v.strip()) < 100:
            raise ValueError('Content too short (< 100 chars)')
        return v

    @validator('title')
    def title_must_exist(cls, v):
        if not v or len(v.strip()) < 5:
            raise ValueError('Title too short or missing')
        return v

    class Config:
        arbitrary_types_allowed = True
