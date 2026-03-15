"""Setup service - environment initialization and verification."""

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from scrapai.exceptions import ScrapAIConfigError


class SetupResult(BaseModel):
    """Result of setup operation."""

    success: bool
    db_url: str
    data_dir: str
    message: str


class VerifyResult(BaseModel):
    """Result of verify operation."""

    success: bool
    checks: dict[str, bool]
    errors: list[str]


def setup() -> SetupResult:
    """Initialize .env, database, and DATA_DIR.

    Returns:
        SetupResult with operation status and details.
    """
    from dotenv import load_dotenv

    load_dotenv()

    db_url = os.getenv("DATABASE_URL", "sqlite:///scrapai.db")
    data_dir = os.getenv("DATA_DIR", "./data")

    data_path = Path(data_dir)
    data_path.mkdir(parents=True, exist_ok=True)

    welcome_file = data_path / "welcome.md"
    if not welcome_file.exists():
        welcome_file.write_text(
            "# Welcome to ScrapAI\n\nThis directory stores your crawl data."
        )

    return SetupResult(
        success=True,
        db_url=db_url,
        data_dir=str(data_path),
        message="Setup completed successfully",
    )


def verify() -> VerifyResult:
    """Verify environment is correctly configured.

    Returns:
        VerifyResult with check results and any errors.
    """
    from dotenv import load_dotenv

    load_dotenv()

    checks: dict[str, bool] = {}
    errors: list[str] = []

    venv_path = Path(".venv")
    if not venv_path.exists():
        checks["venv_exists"] = False
        errors.append("Virtual environment not found")
    else:
        checks["venv_exists"] = True

        try:
            import scrapy
            import sqlalchemy
            import alembic

            checks["dependencies_installed"] = True
        except ImportError as e:
            checks["dependencies_installed"] = False
            errors.append(f"Missing dependencies: {e}")

    data_dir = os.getenv("DATA_DIR", "./data")
    data_path = Path(data_dir)
    if not data_path.exists():
        checks["data_dir_exists"] = False
        errors.append(f"Data directory not found: {data_dir}")
    else:
        checks["data_dir_exists"] = True

    try:
        from core.db import get_db

        db = next(get_db())
        checks["db_connection"] = True
    except Exception as e:
        checks["db_connection"] = False
        errors.append(f"Database connection failed: {e}")

    success = all(checks.values()) if checks else False

    return VerifyResult(success=success, checks=checks, errors=errors)
