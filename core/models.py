from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from .db import Base

_utcnow = lambda: datetime.now(timezone.utc)

class Spider(Base):
    __tablename__ = 'spiders'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    allowed_domains = Column(JSON, nullable=False)
    start_urls = Column(JSON, nullable=False)
    source_url = Column(String, nullable=True)
    active = Column(Boolean, default=True)
    project = Column(String(255), default='default')
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    rules = relationship("SpiderRule", back_populates="spider", cascade="all, delete-orphan")
    settings = relationship("SpiderSetting", back_populates="spider", cascade="all, delete-orphan")
    items = relationship("ScrapedItem", back_populates="spider", cascade="all, delete-orphan")

class SpiderRule(Base):
    __tablename__ = 'spider_rules'

    id = Column(Integer, primary_key=True, index=True)
    spider_id = Column(Integer, ForeignKey('spiders.id'), nullable=False)

    allow_patterns = Column(JSON, nullable=True)
    deny_patterns = Column(JSON, nullable=True)
    restrict_xpaths = Column(JSON, nullable=True)
    restrict_css = Column(JSON, nullable=True)

    callback = Column(String, nullable=True, default=None)
    follow = Column(Boolean, default=True)
    priority = Column(Integer, default=0)

    spider = relationship("Spider", back_populates="rules")

class SpiderSetting(Base):
    __tablename__ = 'spider_settings'

    id = Column(Integer, primary_key=True, index=True)
    spider_id = Column(Integer, ForeignKey('spiders.id'), nullable=False)

    key = Column(String, nullable=False)
    value = Column(String, nullable=False)
    type = Column(String, default='string')

    spider = relationship("Spider", back_populates="settings")

class ScrapedItem(Base):
    __tablename__ = 'scraped_items'

    id = Column(Integer, primary_key=True, index=True)
    spider_id = Column(Integer, ForeignKey('spiders.id'), nullable=False)

    url = Column(String, unique=True, index=True, nullable=False)
    title = Column(String, nullable=True)
    content = Column(Text, nullable=True)
    published_date = Column(DateTime, nullable=True)
    author = Column(String, nullable=True)
    scraped_at = Column(DateTime, default=_utcnow)
    metadata_json = Column(JSON, nullable=True)

    spider = relationship("Spider", back_populates="items")

class CrawlQueue(Base):
    __tablename__ = 'crawl_queue'

    id = Column(Integer, primary_key=True, index=True)
    project_name = Column(String(255), nullable=False, default='default')
    website_url = Column(Text, nullable=False)
    custom_instruction = Column(Text, nullable=True)
    status = Column(String(50), nullable=False, default='pending')
    priority = Column(Integer, nullable=False, default=5)
    processing_by = Column(String(255), nullable=True)
    locked_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)
    completed_at = Column(DateTime, nullable=True)
