#!/usr/bin/env python3
"""
Configuration utilities for the fact-check scrapers project.
"""

import os
import yaml
import json
from typing import Dict, Any, Optional, Union
from utils.logger import get_logger

logger = get_logger("config")

# Define schema for validation
SOURCE_SCHEMA = {
    "module": str,
    "class": str,
    "description": str,
}

def get_project_root() -> str:
    """Get the project root directory."""
    # Start from the current file's directory and go up two levels
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load_yaml_config(config_path: str) -> Dict[str, Any]:
    """
    Load configuration from a YAML file.
    
    Args:
        config_path (str): Path to the YAML configuration file
        
    Returns:
        dict: Configuration dictionary
    """
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        return config
    except Exception as e:
        logger.error(f"Error loading YAML configuration from {config_path}: {e}")
        return {}

def load_sources_config() -> Dict[str, Any]:
    """
    Load the sources configuration.
    
    Returns:
        dict: Sources configuration dictionary
    """
    config_path = os.path.join(get_project_root(), 'config', 'sources.yaml')
    return load_yaml_config(config_path)

def get_crawler_config(source_id: Optional[str] = None) -> Union[Dict[str, Any], Dict[str, Dict[str, Any]]]:
    """
    Get configuration for a specific crawler or all crawlers.
    
    Args:
        source_id (str, optional): Source ID to get crawler configuration for.
                                  If None, returns all crawler configurations.
                                  
    Returns:
        dict: Crawler configuration dictionary
    """
    config = load_sources_config()
    crawlers = config.get('crawlers', {})
    
    if source_id:
        return crawlers.get(source_id, {})
    return crawlers

def get_scraper_config(source_id: Optional[str] = None) -> Union[Dict[str, Any], Dict[str, Dict[str, Any]]]:
    """
    Get configuration for a specific scraper or all scrapers.
    
    Args:
        source_id (str, optional): Source ID to get scraper configuration for.
                                  If None, returns all scraper configurations.
                                  
    Returns:
        dict: Scraper configuration dictionary
    """
    config = load_sources_config()
    scrapers = config.get('scrapers', {})
    
    if source_id:
        return scrapers.get(source_id, {})
    return scrapers

def validate_source_config(config: Dict[str, Any], source_type: str, source_id: str) -> bool:
    """
    Validate a source configuration against the schema.
    
    Args:
        config (dict): Source configuration to validate
        source_type (str): Type of source ('crawler' or 'scraper')
        source_id (str): Source ID
        
    Returns:
        bool: True if the configuration is valid, False otherwise
    """
    # Check required fields
    for field, field_type in SOURCE_SCHEMA.items():
        if field not in config:
            logger.error(f"Missing required field '{field}' in {source_type} configuration for {source_id}")
            return False
        
        if not isinstance(config[field], field_type):
            logger.error(f"Field '{field}' in {source_type} configuration for {source_id} must be of type {field_type.__name__}")
            return False
    
    return True

def validate_all_configs() -> bool:
    """
    Validate all source configurations.
    
    Returns:
        bool: True if all configurations are valid, False otherwise
    """
    config = load_sources_config()
    is_valid = True
    
    # Validate crawler configurations
    for source_id, crawler_config in config.get('crawlers', {}).items():
        if not validate_source_config(crawler_config, 'crawler', source_id):
            is_valid = False
    
    # Validate scraper configurations
    for source_id, scraper_config in config.get('scrapers', {}).items():
        if not validate_source_config(scraper_config, 'scraper', source_id):
            is_valid = False
    
    return is_valid

if __name__ == "__main__":
    # Validate configurations
    if validate_all_configs():
        logger.info("All source configurations are valid")
    else:
        logger.error("Some source configurations are invalid")