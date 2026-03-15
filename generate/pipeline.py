"""End-to-end spider generation pipeline."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import click
from bs4 import BeautifulSoup

from core.config import DATA_DIR
from generate.analyzer import analyze_site
from generate.generator import generate_config
from generate.llm_client import LLMClient
from generate.validator import run_test_crawl
from utils.inspector import inspect_page_async
from utils.url_extractor import extract_urls_from_html

logger = logging.getLogger(__name__)


@dataclass
class LLMConfig:
    api_base: str
    api_key: str
    model: str
    timeout: int = 30


@dataclass
class PipelineResult:
    success: bool
    spider_name: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    failures: Optional[List[Dict[str, str]]] = None


def resolve_llm_config(
    llm_api: Optional[str],
    llm_key: Optional[str],
    llm_model: Optional[str],
    llm_timeout: Optional[int],
) -> LLMConfig:
    api_base = llm_api or os.getenv("SCRAPAI_LLM_API") or "https://api.openai.com/v1"
    api_key = llm_key or os.getenv("SCRAPAI_LLM_KEY")
    model = llm_model or os.getenv("SCRAPAI_LLM_MODEL")
    timeout = llm_timeout or int(os.getenv("SCRAPAI_LLM_TIMEOUT", "30"))

    if not api_key:
        raise ValueError("Missing LLM API key (use --llm-key or SCRAPAI_LLM_KEY)")
    if not model:
        raise ValueError("Missing LLM model (use --llm-model or SCRAPAI_LLM_MODEL)")

    return LLMConfig(api_base=api_base, api_key=api_key, model=model, timeout=timeout)


def _sanitize_text(text: str, secrets: List[str]) -> str:
    sanitized = text
    for secret in secrets:
        if secret and secret in sanitized:
            sanitized = sanitized.replace(secret, f"{secret[:8]}****")
    return sanitized


def _derive_domain_and_name(url: str, project: Optional[str] = None) -> Tuple[str, str]:
    parsed = urlparse(url)
    domain = parsed.netloc
    if domain.endswith("web.archive.org"):
        match = re.search(r"/web/(\d{8})\d*/(?:https?://)?(?:www\.)?([^/]+)", url)
        if match:
            domain = match.group(2)
    domain = domain.replace("www.", "")
    if ":" in domain:
        domain = domain.split(":", 1)[0]
    base_name = domain.replace(".", "_")
    if project:
        spider_name = f"{base_name}_{project}"
    else:
        spider_name = base_name
    return domain, spider_name


def _resolve_inspect_output_dir(url: str, project: str) -> Path:
    parsed = urlparse(url)
    domain = parsed.netloc.replace("www.", "")

    if domain == "web.archive.org":
        match = re.search(r"/web/(\d{8})\d*/(?:https?://)?(?:www\.)?([^/]+)", url)
        if match:
            timestamp = match.group(1)
            original_domain = match.group(2).replace(".", "_").replace(":", "_")
            return (
                Path(DATA_DIR)
                / project
                / "web_archive_org"
                / original_domain
                / timestamp
                / "analysis"
            )
        return Path(DATA_DIR) / project / "web_archive_org" / "analysis"

    source_id = domain.replace(".", "_")
    return Path(DATA_DIR) / project / source_id / "analysis"


def _detect_js_signals(html: str, soup: BeautifulSoup) -> List[str]:
    signals: List[str] = []
    lower = html.lower()

    if "checking your browser" in lower or "cf-browser-verification" in lower:
        signals.append("cloudflare_check")
    if "__next_data__" in lower or "data-reactroot" in lower:
        signals.append("react_app")
    if "window.__nuxt__" in lower or 'id="__nuxt"' in lower:
        signals.append("nuxt_app")
    if "ng-version" in lower or "ng-app" in lower:
        signals.append("angular_app")
    if "enable javascript" in lower or "requires javascript" in lower:
        signals.append("js_required_text")

    scripts = soup.find_all("script")
    text_len = len(soup.get_text(strip=True))
    if text_len < 200 and len(scripts) > 20:
        signals.append("low_text_high_script")

    return signals


def _should_use_browser(signals: List[str]) -> bool:
    if not signals:
        return False
    strong = {"cloudflare_check", "js_required_text"}
    if any(s in strong for s in signals):
        return True
    return "low_text_high_script" in signals


def _selector_from_element(el) -> str:
    if el.get("id"):
        return f"{el.name}#{el.get('id')}"
    classes = el.get("class", [])
    if classes:
        return f"{el.name}." + ".".join(classes)
    return el.name


def _build_selector_candidates(soup: BeautifulSoup) -> Dict[str, Any]:
    candidates: Dict[str, Any] = {
        "titles": [],
        "content_containers": [],
        "dates": [],
        "authors": [],
    }

    for tag in ["h1", "h2"]:
        for el in soup.find_all(tag)[:5]:
            text = el.get_text(strip=True)[:120]
            if text:
                candidates["titles"].append(
                    {"selector": _selector_from_element(el), "text": text}
                )

    content_keywords = ["article", "content", "body", "post", "entry", "story"]
    containers = []
    for el in soup.find_all(["article", "div", "section", "main"]):
        classes = " ".join(el.get("class", [])).lower()
        if el.name == "article" or any(kw in classes for kw in content_keywords):
            text_len = len(el.get_text(strip=True))
            if text_len > 200:
                containers.append((el, text_len))
    containers.sort(key=lambda x: x[1], reverse=True)
    for el, text_len in containers[:5]:
        candidates["content_containers"].append(
            {"selector": _selector_from_element(el), "text_length": text_len}
        )

    date_keywords = ["date", "time", "published", "posted", "updated"]
    for el in soup.find_all(["time", "span", "div", "p"]):
        classes = " ".join(el.get("class", [])).lower()
        if el.name == "time" or any(kw in classes for kw in date_keywords):
            text = el.get_text(strip=True)[:80]
            if text:
                candidates["dates"].append(
                    {"selector": _selector_from_element(el), "text": text}
                )
        if len(candidates["dates"]) >= 5:
            break

    author_keywords = ["author", "byline", "writer", "by"]
    for el in soup.find_all(["span", "div", "a", "p"]):
        classes = " ".join(el.get("class", [])).lower()
        if any(kw in classes for kw in author_keywords):
            text = el.get_text(strip=True)[:80]
            if text:
                candidates["authors"].append(
                    {"selector": _selector_from_element(el), "text": text}
                )
        if len(candidates["authors"]) >= 5:
            break

    return candidates


def _truncate(text: str, max_chars: int = 20000) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...[truncated]..."


def _build_inspect_summary(
    url: str,
    html: str,
    js_signals: List[str],
    mode: str,
    html_path: Path,
) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "lxml")
    selectors = _build_selector_candidates(soup)

    urls = extract_urls_from_html(str(html_path))
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    url_samples = []
    seen = set()
    for u in urls:
        abs_url = urljoin(base, u)
        if abs_url not in seen:
            seen.add(abs_url)
            url_samples.append(abs_url)
        if len(url_samples) >= 50:
            break

    return {
        "url": url,
        "fetch_mode": mode,
        "js_rendering_signals": js_signals,
        "html_title": soup.title.text.strip() if soup.title else None,
        "html_snapshot": _truncate(html),
        "selector_candidates": selectors,
        "url_samples": url_samples,
    }


def _load_examples() -> List[Dict[str, Any]]:
    root = Path(__file__).resolve().parent.parent
    examples = []
    for name in ["spider-ecommerce.json", "spider-jobs.json", "spider-realestate.json"]:
        path = root / "templates" / name
        if not path.exists():
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                examples.append(json.load(f))
        except Exception:
            continue
    return examples[:3]


async def _inspect_site(url: str, project: str) -> Dict[str, Any]:
    output_dir = _resolve_inspect_output_dir(url, project)
    output_dir.mkdir(parents=True, exist_ok=True)

    html_path = output_dir / "page.html"
    if html_path.exists():
        html_path.unlink()

    await inspect_page_async(
        url,
        output_dir=str(output_dir),
        proxy_type="auto",
        save_html=True,
        mode="http",
        project=project,
    )

    if not html_path.exists():
        await inspect_page_async(
            url,
            output_dir=str(output_dir),
            proxy_type="auto",
            save_html=True,
            mode="browser",
            project=project,
        )
        if not html_path.exists():
            raise RuntimeError("Inspect failed to produce page.html")
        html = html_path.read_text(encoding="utf-8", errors="ignore")
        soup = BeautifulSoup(html, "lxml")
        js_signals = _detect_js_signals(html, soup)
        return _build_inspect_summary(url, html, js_signals, "browser", html_path)

    html = html_path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(html, "lxml")
    js_signals = _detect_js_signals(html, soup)

    mode = "http"
    if _should_use_browser(js_signals):
        await inspect_page_async(
            url,
            output_dir=str(output_dir),
            proxy_type="auto",
            save_html=True,
            mode="browser",
            project=project,
        )
        html = html_path.read_text(encoding="utf-8", errors="ignore")
        soup = BeautifulSoup(html, "lxml")
        js_signals = _detect_js_signals(html, soup)
        mode = "browser"

    return _build_inspect_summary(url, html, js_signals, mode, html_path)


async def run_add_pipeline(
    url: str,
    project: str,
    description: str,
    llm: LLMConfig,
    dry_run: bool,
    output_path: Optional[Path],
    backup: bool,
    skip_test_crawl: bool = False,
) -> PipelineResult:
    secrets = [llm.api_key]

    domain, spider_name = _derive_domain_and_name(url, project)
    spider_analysis_dir = Path(DATA_DIR) / project / spider_name / "analysis"
    spider_analysis_dir.mkdir(parents=True, exist_ok=True)

    click.echo(f"[1/4] Inspecting {url} ...")
    inspect_summary = await _inspect_site(url, project)

    examples = _load_examples()

    backup_path = Path.cwd() / f"{spider_name}.backup.json"
    had_existing = False
    if not dry_run:
        had_existing = _spider_exists(spider_name, project)

    client = LLMClient(
        api_base=llm.api_base,
        api_key=llm.api_key,
        model=llm.model,
        timeout=llm.timeout,
    )

    try:
        click.echo(f"[2/4] Analyzing page structure with {llm.model} ...")
        analysis = await analyze_site(client, inspect_summary, description)

        click.echo("[3/4] Generating spider config ...")
        config = await generate_config(
            client=client,
            inspect_summary=inspect_summary,
            analysis=analysis,
            description=description,
            examples=examples,
            name=spider_name,
            source_url=url,
            allowed_domain=domain,
        )

        if dry_run:
            _write_output_files(
                spider_analysis_dir, output_path, config, always_write=True
            )
            click.echo(json.dumps(config, indent=2))
            click.echo("✅ Dry run complete. No DB changes made.")
            return PipelineResult(success=True, spider_name=spider_name, config=config)

        if backup and had_existing:
            _maybe_backup_existing(spider_name, project, backup_path)

        _import_spider_config(config, project)

        if skip_test_crawl:
            _write_output_files(
                spider_analysis_dir, output_path, config, always_write=True
            )
            click.echo("⚠️  Test crawl skipped (--skip-test-crawl)")
            click.echo(f"✅ Spider '{spider_name}' generated and imported.")
            return PipelineResult(success=True, spider_name=spider_name, config=config)

        click.echo("[4/4] Validating with test crawl (limit=3) ...")
        items_count = await asyncio.to_thread(run_test_crawl, spider_name, project, 3)
        if items_count < 1:
            raise RuntimeError("Test crawl returned 0 items")

        _write_output_files(spider_analysis_dir, output_path, config, always_write=True)
        click.echo(f"✅ Spider '{spider_name}' generated and imported.")
        return PipelineResult(success=True, spider_name=spider_name, config=config)

    except Exception as exc:
        message = _sanitize_text(str(exc), secrets)
        logger.debug("LLM run failed: %s", message)
        if not dry_run:
            _restore_or_cleanup(spider_name, project, backup_path, had_existing)
        return PipelineResult(
            success=False,
            spider_name=spider_name,
            error=f"LLM attempt failed: {message}",
        )


def _write_output_files(
    analysis_dir: Path,
    output_path: Optional[Path],
    config: Dict[str, Any],
    always_write: bool = True,
) -> None:
    if always_write:
        analysis_path = analysis_dir / "final_spider.json"
        with open(analysis_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)


def _maybe_backup_existing(spider_name: str, project: str, backup_path: Path) -> bool:
    from core.db import get_db
    from core.models import Spider
    from core.spider_store import serialize_spider_config

    db = next(get_db())
    try:
        existing = (
            db.query(Spider)
            .filter(Spider.name == spider_name, Spider.project == project)
            .first()
        )
        if not existing:
            return False
        data = serialize_spider_config(existing)
        with open(backup_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(
            "Overwriting spider '%s' (id=%s) after backup to %s",
            spider_name,
            existing.id,
            backup_path,
        )
        return True
    finally:
        db.close()


def _import_spider_config(config: Dict[str, Any], project: str) -> None:
    from core.db import get_db
    from core.spider_store import upsert_spider_config

    db = next(get_db())
    try:
        upsert_spider_config(db, config, project, skip_validation=False)
    finally:
        db.close()


def _restore_or_cleanup(
    spider_name: str, project: str, backup_path: Path, had_existing: bool
) -> None:
    if had_existing and backup_path.exists():
        try:
            with open(backup_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return
        from core.db import get_db
        from core.spider_store import upsert_spider_config

        db = next(get_db())
        try:
            upsert_spider_config(
                db, data, project, skip_validation=True, validate_name_match=False
            )
        finally:
            db.close()
        return

    if had_existing:
        return

    # No previous spider: delete newly created if present
    from core.db import get_db
    from core.models import Spider

    db = next(get_db())
    try:
        spider = (
            db.query(Spider)
            .filter(Spider.name == spider_name, Spider.project == project)
            .first()
        )
        if spider:
            db.delete(spider)
            db.commit()
    finally:
        db.close()


def _spider_exists(spider_name: str, project: str) -> bool:
    from core.db import get_db
    from core.models import Spider

    db = next(get_db())
    try:
        return (
            db.query(Spider)
            .filter(Spider.name == spider_name, Spider.project == project)
            .first()
            is not None
        )
    finally:
        db.close()
