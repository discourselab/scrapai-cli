"""
Configuration module for ScrapAI

Loads settings from .env file with sensible defaults.
Settings can be overridden via environment variables.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
# Look for .env in the project root (parent of core/)
project_root = Path(__file__).parent.parent
dotenv_path = project_root / '.env'
load_dotenv(dotenv_path)

# Data directory - where all scraped data, analysis, and artifacts are stored
DATA_DIR = os.getenv('DATA_DIR', './data')

# Database configuration
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://localhost/scrapai')

# Logging configuration
LOG_LEVEL = os.getenv('LOG_LEVEL', 'info')
LOG_DIR = os.getenv('LOG_DIR', './logs')

# Create data directory if it doesn't exist
Path(DATA_DIR).mkdir(parents=True, exist_ok=True)
