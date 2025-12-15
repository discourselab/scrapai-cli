from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from .db import Base

class Spider(Base):
    __tablename__ = 'spiders'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    allowed_domains = Column(JSON, nullable=False)
    start_urls = Column(JSON, nullable=False)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    rules = relationship("SpiderRule", back_populates="spider", cascade="all, delete-orphan")
    settings = relationship("SpiderSetting", back_populates="spider", cascade="all, delete-orphan")
    items = relationship("ScrapedItem", back_populates="spider", cascade="all, delete-orphan")

class SpiderRule(Base):
    __tablename__ = 'spider_rules'

    id = Column(Integer, primary_key=True, index=True)
    spider_id = Column(Integer, ForeignKey('spiders.id'), nullable=False)
    
    # Rule configuration
    allow_patterns = Column(JSON, nullable=True)  # List of regex strings
    deny_patterns = Column(JSON, nullable=True)   # List of regex strings
    restrict_xpaths = Column(JSON, nullable=True) # List of xpath strings
    restrict_css = Column(JSON, nullable=True)    # List of css strings

    callback = Column(String, nullable=True, default=None)
    follow = Column(Boolean, default=True)
    priority = Column(Integer, default=0)
    
    spider = relationship("Spider", back_populates="rules")

class SpiderSetting(Base):
    __tablename__ = 'spider_settings'

    id = Column(Integer, primary_key=True, index=True)
    spider_id = Column(Integer, ForeignKey('spiders.id'), nullable=False)
    
    key = Column(String, nullable=False)
    value = Column(String, nullable=False) # Stored as string, cast on load
    type = Column(String, default='string') # string, int, float, bool
    
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
    scraped_at = Column(DateTime, default=datetime.utcnow)
    metadata_json = Column(JSON, nullable=True) # Renamed to avoid conflict with metadata attribute

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
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
