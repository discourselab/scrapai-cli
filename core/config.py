"""
Configuration module for ScrapAI

Loads settings from .env file with sensible defaults.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

project_root = Path(__file__).parent.parent
dotenv_path = project_root / ".env"
load_dotenv(dotenv_path)

DATA_DIR = os.getenv("DATA_DIR", "./data")

LOG_LEVEL = os.getenv("LOG_LEVEL", "info")
LOG_DIR = os.getenv("LOG_DIR", "./logs")

Path(DATA_DIR).mkdir(parents=True, exist_ok=True)
