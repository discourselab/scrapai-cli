"""Helpers for importing/exporting spider configs to/from the database."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from core.models import Spider, SpiderRule, SpiderSetting
from core.schemas import SpiderConfigSchema


def serialize_spider_config(spider: Spider) -> Dict[str, Any]:
    rules = []
    for r in spider.rules:
        rules.append(
            {
                "allow": r.allow_patterns,
                "deny": r.deny_patterns,
                "restrict_xpaths": r.restrict_xpaths,
                "restrict_css": r.restrict_css,
                "callback": r.callback,
                "follow": r.follow,
                "priority": r.priority,
            }
        )

    settings: Dict[str, Any] = {}
    for s in spider.settings:
        settings[s.key] = _deserialize_setting_value(s.value, s.type)

    data: Dict[str, Any] = {
        "name": spider.name,
        "source_url": spider.source_url,
        "allowed_domains": spider.allowed_domains,
        "start_urls": spider.start_urls,
        "rules": rules,
        "settings": settings,
    }
    if spider.callbacks_config is not None:
        data["callbacks"] = spider.callbacks_config

    return data


def upsert_spider_config(
    db,
    config: Dict[str, Any],
    project: str,
    skip_validation: bool = False,
    validate_name_match: bool = True,
) -> Spider:
    if skip_validation:
        data = dict(config)
    else:
        validated = SpiderConfigSchema(**config)
        data = validated.model_dump(exclude_none=True)

    spider_name = data["name"]
    allowed_domains = data.get("allowed_domains") or []
    start_urls = data.get("start_urls") or []
    source_url = data.get("source_url")
    rules = data.get("rules") or []
    settings_dict = data.get("settings") or {}
    callbacks_dict = data.get("callbacks")

    if validate_name_match and source_url:
        _validate_name_matches_source(spider_name, source_url)

    existing = (
        db.query(Spider)
        .filter(Spider.name == spider_name, Spider.project == project)
        .first()
    )

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
    return spider


def _deserialize_setting_value(value: str, type_name: Optional[str]) -> Any:
    if type_name == "json":
        try:
            return json.loads(value)
        except Exception:
            return value
    if type_name == "int":
        try:
            return int(value)
        except Exception:
            return value
    if type_name == "float":
        try:
            return float(value)
        except Exception:
            return value
    if type_name == "bool":
        return str(value).lower() in ["true", "1", "yes"]
    return value


def _validate_name_matches_source(spider_name: str, source_url: str) -> None:
    from urllib.parse import urlparse

    parsed_url = urlparse(source_url)
    domain = parsed_url.netloc.replace("www.", "")
    base_name = domain.replace(".", "_")
    if spider_name != base_name and not spider_name.startswith(f"{base_name}_"):
        raise ValueError(
            f"Spider name '{spider_name}' must be '{base_name}' or '{base_name}_<project>'."
        )
