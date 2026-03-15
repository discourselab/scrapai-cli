"""Spider management service."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from scrapai.exceptions import SpiderNotFoundError, ValidationError


class SpiderInfo(BaseModel):
    """Spider information model."""

    name: str
    project: str
    start_urls: list[str]
    config: dict
    created_at: datetime | None
    last_crawled_at: datetime | None
    last_crawl_item_count: int | None


class GenerateSpiderResult(BaseModel):
    """Result of spider generation."""

    name: str
    project: str
    config: dict
    imported: bool
    generated_at: datetime
    test_crawl_item_count: int | None = None


def list_spiders(project: str | None = None) -> list[SpiderInfo]:
    """List all spiders in the database.

    Args:
        project: Optional project filter.

    Returns:
        List of SpiderInfo objects.
    """
    from core.db import get_db
    from core.models import Spider, ScrapedItem
    from sqlalchemy import func

    db = next(get_db())

    query = db.query(Spider)
    if project:
        query = query.filter(Spider.project == project)

    spiders = query.all()

    result = []
    for s in spiders:
        last_item = (
            db.query(ScrapedItem)
            .filter(ScrapedItem.spider_id == s.id)
            .order_by(ScrapedItem.scraped_at.desc())
            .first()
        )

        item_count = None
        if last_item:
            count = (
                db.query(func.count(ScrapedItem.id))
                .filter(ScrapedItem.spider_id == s.id)
                .scalar()
            )
            item_count = count

        config = {
            "name": s.name,
            "allowed_domains": s.allowed_domains,
            "start_urls": s.start_urls,
            "source_url": s.source_url,
            "active": s.active,
            "callbacks_config": s.callbacks_config,
        }

        result.append(
            SpiderInfo(
                name=s.name,
                project=s.project or "default",
                start_urls=s.start_urls or [],
                config=config,
                created_at=s.created_at,
                last_crawled_at=last_item.scraped_at if last_item else None,
                last_crawl_item_count=item_count,
            )
        )

    return result


def get_spider(name: str, project: str) -> SpiderInfo:
    """Get a single spider's config and metadata.

    Args:
        name: Spider name.
        project: Project name.

    Returns:
        SpiderInfo object.

    Raises:
        SpiderNotFoundError: If spider not found.
    """
    from core.db import get_db
    from core.models import Spider, ScrapedItem
    from sqlalchemy import func

    db = next(get_db())

    spider = (
        db.query(Spider).filter(Spider.name == name, Spider.project == project).first()
    )

    if not spider:
        raise SpiderNotFoundError(name, project)

    last_item = (
        db.query(ScrapedItem)
        .filter(ScrapedItem.spider_id == spider.id)
        .order_by(ScrapedItem.scraped_at.desc())
        .first()
    )

    item_count = None
    if last_item:
        count = (
            db.query(func.count(ScrapedItem.id))
            .filter(ScrapedItem.spider_id == spider.id)
            .scalar()
        )
        item_count = count

    config = {
        "name": spider.name,
        "allowed_domains": spider.allowed_domains,
        "start_urls": spider.start_urls,
        "source_url": spider.source_url,
        "active": spider.active,
        "callbacks_config": spider.callbacks_config,
    }

    return SpiderInfo(
        name=spider.name,
        project=spider.project or "default",
        start_urls=spider.start_urls or [],
        config=config,
        created_at=spider.created_at,
        last_crawled_at=last_item.scraped_at if last_item else None,
        last_crawl_item_count=item_count,
    )


def import_spider(
    config: dict | Path,
    project: str,
    skip_validation: bool = False,
) -> SpiderInfo:
    """Import or overwrite a spider from a dict or JSON file.

    Args:
        config: Spider config dict or Path to JSON file.
        project: Project name.
        skip_validation: Skip Pydantic validation.

    Returns:
        SpiderInfo of imported spider.

    Raises:
        ValidationError: If config validation fails.
    """
    from core.db import get_db
    from core.models import Spider, SpiderRule, SpiderSetting
    from core.schemas import SpiderConfigSchema
    from pydantic import ValidationError as PydanticValidationError

    db = next(get_db())

    if isinstance(config, (str, Path)):
        config_path = Path(config)
        if not config_path.exists():
            raise ValidationError(f"File not found: {config}")
        with open(config_path, "r") as f:
            data = json.load(f)
    else:
        data = config

    if skip_validation:
        spider_name = data["name"]
        allowed_domains = data.get("allowed_domains", [])
        start_urls = data.get("start_urls", [])
        source_url = data.get("source_url")
        rules = data.get("rules", [])
        settings_dict = data.get("settings", {})
        callbacks_dict = data.get("callbacks")
    else:
        try:
            validated = SpiderConfigSchema(**data)
            spider_name = validated.name
            allowed_domains = validated.allowed_domains
            start_urls = validated.start_urls
            source_url = validated.source_url
            rules = [r.model_dump() for r in validated.rules]
            settings_dict = validated.settings.model_dump(
                exclude_none=True, exclude_unset=True
            )
            callbacks_dict = None
            if validated.callbacks:
                callbacks_dict = {
                    name: cb.model_dump() for name, cb in validated.callbacks.items()
                }
        except PydanticValidationError as e:
            errors = [
                f"{' -> '.join(str(x) for x in err['loc'])}: {err['msg']}"
                for err in e.errors()
            ]
            raise ValidationError(f"Validation failed: {', '.join(errors)}")

    existing = db.query(Spider).filter(Spider.name == spider_name).first()
    if existing:
        existing.allowed_domains = allowed_domains
        existing.start_urls = start_urls
        existing.source_url = source_url
        existing.project = project
        existing.callbacks_config = callbacks_dict

        db.query(SpiderRule).filter(SpiderRule.spider_id == existing.id).delete()
        db.query(SpiderSetting).filter(SpiderSetting.spider_id == existing.id).delete()
        spider = existing
    else:
        spider = Spider(
            name=spider_name,
            allowed_domains=allowed_domains,
            start_urls=start_urls,
            source_url=source_url,
            project=project,
            callbacks_config=callbacks_dict,
        )
        db.add(spider)
        db.flush()

    for rule_data in rules:
        rule = SpiderRule(
            spider_id=spider.id,
            allow_patterns=rule_data.get("allow"),
            deny_patterns=rule_data.get("deny"),
            restrict_xpaths=rule_data.get("restrict_xpaths"),
            restrict_css=rule_data.get("restrict_css"),
            callback=rule_data.get("callback"),
            follow=rule_data.get("follow", True),
            priority=rule_data.get("priority", 0),
        )
        db.add(rule)

    for k, v in settings_dict.items():
        if isinstance(v, (list, dict)):
            value_str = json.dumps(v)
            type_name = "json"
        else:
            value_str = str(v)
            type_name = type(v).__name__

        setting = SpiderSetting(
            spider_id=spider.id, key=k, value=value_str, type=type_name
        )
        db.add(setting)

    db.commit()

    return get_spider(spider_name, project)


def export_spider(name: str, project: str) -> dict:
    """Export a spider's raw JSON config as a dict.

    Args:
        name: Spider name.
        project: Project name.

    Returns:
        Spider config dict.

    Raises:
        SpiderNotFoundError: If spider not found.
    """
    from core.db import get_db
    from core.models import Spider, SpiderRule, SpiderSetting

    db = next(get_db())

    spider = (
        db.query(Spider).filter(Spider.name == name, Spider.project == project).first()
    )

    if not spider:
        raise SpiderNotFoundError(name, project)

    rules = db.query(SpiderRule).filter(SpiderRule.spider_id == spider.id).all()
    settings = (
        db.query(SpiderSetting).filter(SpiderSetting.spider_id == spider.id).all()
    )

    config = {
        "name": spider.name,
        "allowed_domains": spider.allowed_domains,
        "start_urls": spider.start_urls,
        "source_url": spider.source_url,
        "rules": [],
        "settings": {},
        "callbacks": spider.callbacks_config,
    }

    for rule in rules:
        rule_dict = {}
        if rule.allow_patterns:
            rule_dict["allow"] = rule.allow_patterns
        if rule.deny_patterns:
            rule_dict["deny"] = rule.deny_patterns
        if rule.restrict_xpaths:
            rule_dict["restrict_xpaths"] = rule.restrict_xpaths
        if rule.restrict_css:
            rule_dict["restrict_css"] = rule.restrict_css
        if rule.callback:
            rule_dict["callback"] = rule.callback
        if rule.follow is not None:
            rule_dict["follow"] = rule.follow
        if rule.priority:
            rule_dict["priority"] = rule.priority
        if rule_dict:
            config["rules"].append(rule_dict)

    for setting in settings:
        if setting.type == "json":
            config["settings"][setting.key] = json.loads(setting.value)
        else:
            config["settings"][setting.key] = setting.value

    return config


def delete_spider(name: str, project: str) -> None:
    """Delete a spider and its scraped data.

    Args:
        name: Spider name.
        project: Project name.

    Raises:
        SpiderNotFoundError: If spider not found.
    """
    from core.db import get_db
    from core.models import Spider, ScrapedItem, SpiderRule, SpiderSetting

    db = next(get_db())

    spider = (
        db.query(Spider).filter(Spider.name == name, Spider.project == project).first()
    )

    if not spider:
        raise SpiderNotFoundError(name, project)

    db.query(ScrapedItem).filter(ScrapedItem.spider_id == spider.id).delete()
    db.query(SpiderRule).filter(SpiderRule.spider_id == spider.id).delete()
    db.query(SpiderSetting).filter(SpiderSetting.spider_id == spider.id).delete()
    db.delete(spider)
    db.commit()
