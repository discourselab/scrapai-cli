"""
Data schemas for factcheck-scrapers.

This module defines schemas for validating data structures used in the project,
such as article data, configuration files, etc.
"""

import json
import os
from typing import Any, Dict, List, Optional, Union
from jsonschema import validate, ValidationError

# Base article schema
ARTICLE_SCHEMA = {
    "type": "object",
    "required": ["id", "url", "title", "published_date"],
    "properties": {
        "id": {"type": "string"},
        "url": {"type": "string", "format": "uri"},
        "title": {"type": "string"},
        "published_date": {"type": "string", "format": "date-time"},
        "authors": {
            "type": "array",
            "items": {"type": "string"}
        },
        "category": {"type": ["string", "null"]},
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["text"],
                "properties": {
                    "text": {"type": "string"},
                    "rating": {"type": ["string", "null"]},
                    "source": {"type": ["string", "null"]},
                    "source_url": {"type": ["string", "null"], "format": "uri"}
                }
            }
        },
        "content": {"type": ["string", "null"]},
        "content_html": {"type": ["string", "null"]},
        "summary": {"type": ["string", "null"]},
        "rating": {"type": ["string", "null"]},
        "tags": {
            "type": "array",
            "items": {"type": "string"}
        },
        "metadata": {
            "type": "object",
            "additionalProperties": True
        }
    },
    "additionalProperties": True
}

# Articles collection schema
ARTICLES_SCHEMA = {
    "type": "object",
    "required": ["source", "last_updated", "articles"],
    "properties": {
        "source": {"type": "string"},
        "last_updated": {"type": "string", "format": "date-time"},
        "articles": {
            "type": "array",
            "items": ARTICLE_SCHEMA
        }
    }
}

# State file schema
STATE_SCHEMA = {
    "type": "object",
    "required": ["source", "last_crawled"],
    "properties": {
        "source": {"type": "string"},
        "last_crawled": {"type": "string", "format": "date-time"},
        "latest_article_date": {"type": ["string", "null"], "format": "date-time"},
        "latest_article_id": {"type": ["string", "null"]},
        "crawl_state": {"type": "object", "additionalProperties": True}
    },
    "additionalProperties": True
}

def validate_article(article_data: Dict[str, Any]) -> bool:
    """
    Validate an article against the article schema.
    
    Args:
        article_data: Article data to validate
        
    Returns:
        bool: True if valid, False otherwise
        
    Raises:
        ValidationError: If validation fails
    """
    try:
        validate(instance=article_data, schema=ARTICLE_SCHEMA)
        return True
    except ValidationError as e:
        raise ValidationError(f"Article validation failed: {e}")

def validate_articles_file(articles_data: Dict[str, Any]) -> bool:
    """
    Validate an articles file against the articles schema.
    
    Args:
        articles_data: Articles data to validate
        
    Returns:
        bool: True if valid, False otherwise
        
    Raises:
        ValidationError: If validation fails
    """
    try:
        validate(instance=articles_data, schema=ARTICLES_SCHEMA)
        return True
    except ValidationError as e:
        raise ValidationError(f"Articles file validation failed: {e}")

def validate_state_file(state_data: Dict[str, Any]) -> bool:
    """
    Validate a state file against the state schema.
    
    Args:
        state_data: State data to validate
        
    Returns:
        bool: True if valid, False otherwise
        
    Raises:
        ValidationError: If validation fails
    """
    try:
        validate(instance=state_data, schema=STATE_SCHEMA)
        return True
    except ValidationError as e:
        raise ValidationError(f"State file validation failed: {e}")

def load_and_validate_article(article_path: str) -> Dict[str, Any]:
    """
    Load and validate an article from a file.
    
    Args:
        article_path: Path to the article file
        
    Returns:
        dict: Validated article data
        
    Raises:
        ValidationError: If validation fails
        FileNotFoundError: If the file doesn't exist
        json.JSONDecodeError: If the file isn't valid JSON
    """
    with open(article_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    validate_article(data)
    return data

def load_and_validate_articles_file(articles_path: str) -> Dict[str, Any]:
    """
    Load and validate an articles file.
    
    Args:
        articles_path: Path to the articles file
        
    Returns:
        dict: Validated articles data
        
    Raises:
        ValidationError: If validation fails
        FileNotFoundError: If the file doesn't exist
        json.JSONDecodeError: If the file isn't valid JSON
    """
    with open(articles_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    validate_articles_file(data)
    return data

def load_and_validate_state_file(state_path: str) -> Dict[str, Any]:
    """
    Load and validate a state file.
    
    Args:
        state_path: Path to the state file
        
    Returns:
        dict: Validated state data
        
    Raises:
        ValidationError: If validation fails
        FileNotFoundError: If the file doesn't exist
        json.JSONDecodeError: If the file isn't valid JSON
    """
    with open(state_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    validate_state_file(data)
    return data