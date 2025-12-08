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
