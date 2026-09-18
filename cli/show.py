import json
from pathlib import Path

import click


def _matches(rec, url, text, title):
    """Case-insensitive substring filters, mirroring the DB branch's ilike."""

    def has(field, needle):
        return needle.lower() in str(rec.get(field) or "").lower()

    if url and not has("url", url):
        return False
    if title and not has("title", title):
        return False
    if text and not (has("title", text) or has("content", text)):
        return False
    return True


def _read_crawl_rows(crawls_dir, limit, url=None, text=None, title=None):
    """(rows, file_count): the newest matching rows from crawl_*.jsonl.

    Newest file first (mtime), rows within a file scanned bottom-up — crawl
    files are append-only, so the last lines are the newest items. Mirrors the
    DB branch's ORDER BY scraped_at DESC."""
    files = sorted(
        Path(crawls_dir).glob("crawl_*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    rows = []
    for f in files:
        try:
            # ponytail: whole-file read to walk lines newest-first; fine at
            # observed corpus sizes (tens of MB) — stream if files grow to GBs.
            lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if not _matches(rec, url, text, title):
                continue
            rows.append(rec)
            if len(rows) >= limit:
                return rows, len(files)
    return rows, len(files)


# Bulky or bookkeeping row fields never shown as extra metadata.
_SHOWN_OR_SKIPPED = {
    "url",
    "title",
    "content",
    "author",
    "published_date",
    "scraped_at",
    "html",
    "clean_html",
    "spider_id",
    "spider_name",
    "source",
    "_callback",
    "extracted_at",
}


def _echo_crawl_row(i, rec):
    """Render one JSONL row like the DB branch renders an article."""
    pub = str(rec.get("published_date") or "Unknown")[:10]
    scraped = str(rec.get("scraped_at") or "Unknown")[:16].replace("T", " ")
    click.echo(f"🔸 [{i}] {rec.get('title') or 'No Title'}")
    click.echo(f"   📅 Published: {pub} | Scraped: {scraped}")
    click.echo(f"   🔗 {rec.get('url')}")
    if rec.get("author"):
        click.echo(f"   ✍️  {rec['author']}")
    content = rec.get("content") or ""
    if content:
        preview = content[:150].replace("\n", " ").strip()
        if len(content) > 150:
            preview += "..."
        click.echo(f"   📝 {preview}")
    extras = {}
    for k, v in rec.items():
        if k in _SHOWN_OR_SKIPPED or v in (None, "", []):
            continue
        if k == "metadata_json" and isinstance(v, dict):
            extras.update(v)
        else:
            extras[k] = v
    for k, v in extras.items():
        v = str(v)
        if len(v) > 100:
            v = v[:100] + "..."
        click.echo(f"   • {k}: {v}")
    click.echo()


@click.command()
@click.argument("spider_name")
@click.option("--project", required=True, help="Project name (required)")
@click.option(
    "--limit", "-l", type=int, default=5, help="Number of articles to show (default: 5)"
)
@click.option("--url", default=None, help="Filter by URL pattern")
@click.option("--text", "-t", default=None, help="Search title or content")
@click.option("--title", default=None, help="Search titles only")
@click.option(
    "--source",
    type=click.Choice(["auto", "crawls", "db"]),
    default="auto",
    help=(
        "auto (default): production crawls/*.jsonl when present, else the DB; "
        "crawls/db force one source (db = test-crawl items)"
    ),
)
def show(spider_name, project, limit, url, text, title, source):
    """Show scraped articles (production crawl output by default, DB fallback).

    Production crawls write crawls/*.jsonl, never DB rows; the DB holds only
    --limit test-crawl items. Showing the DB for a production spider
    misrepresented what it collected (docs/requests/20), so crawl files win
    when they exist.
    """
    from core.config import DATA_DIR

    crawls_dir = Path(DATA_DIR) / project / spider_name / "crawls"
    use_crawls = source == "crawls" or (
        source == "auto" and any(crawls_dir.glob("crawl_*.jsonl"))
    )

    if use_crawls:
        rows, nfiles = _read_crawl_rows(crawls_dir, limit, url, text, title)
        filters_applied = [
            f"{label} contains '{needle}'"
            for label, needle in (
                ("URL", url),
                ("title", title),
                ("title or content", text),
            )
            if needle
        ]
        if not rows:
            click.echo(
                f"📭 No matching items in production crawl files for "
                f"'{spider_name}' ({nfiles} files)"
            )
            if filters_applied:
                click.echo(f"   (with filters: {', '.join(filters_applied)})")
            click.echo("   (test-crawl items live in the DB: --source db)")
            return
        click.echo(
            f"📰 Showing {len(rows)} newest items from production crawls "
            f"({nfiles} files) for '{spider_name}':"
        )
        if filters_applied:
            click.echo(f"   (filtered by: {', '.join(filters_applied)})")
        click.echo()
        for i, rec in enumerate(rows, 1):
            _echo_crawl_row(i, rec)
        return

    if source == "auto":
        click.echo("ℹ️  No production crawl files — showing DB (test-crawl) items.")
    else:
        click.echo("ℹ️  Source: DB (test-crawl items).")

    from core.db import get_db
    from core.models import Spider, ScrapedItem

    with get_db() as db:
        spider = (
            db.query(Spider)
            .filter(Spider.name == spider_name, Spider.project == project)
            .first()
        )

        if not spider:
            click.echo(f"❌ Spider '{spider_name}' not found in project '{project}'")
            return

        query = db.query(ScrapedItem).filter(ScrapedItem.spider_id == spider.id)

        filters_applied = []
        if url:
            query = query.filter(ScrapedItem.url.ilike(f"%{url}%"))
            filters_applied.append(f"URL contains '{url}'")
        if title:
            query = query.filter(ScrapedItem.title.ilike(f"%{title}%"))
            filters_applied.append(f"title contains '{title}'")
        if text:
            from sqlalchemy import or_

            query = query.filter(
                or_(
                    ScrapedItem.title.ilike(f"%{text}%"),
                    ScrapedItem.content.ilike(f"%{text}%"),
                )
            )
            filters_applied.append(f"title or content contains '{text}'")

        items = query.order_by(ScrapedItem.scraped_at.desc()).limit(limit).all()

        if not items:
            click.echo(f"📭 No articles found for spider '{spider_name}'")
            if filters_applied:
                click.echo(f"   (with filters: {', '.join(filters_applied)})")
            return

        click.echo(f"📰 Showing {len(items)} articles from '{spider_name}':")
        if filters_applied:
            click.echo(f"   (filtered by: {', '.join(filters_applied)})")
        click.echo()

        # Load spider callbacks config (source of truth for field definitions)
        callbacks_config = spider.callbacks_config or {}

        for i, item in enumerate(items, 1):
            scraped_date = (
                item.scraped_at.strftime("%Y-%m-%d %H:%M")
                if item.scraped_at
                else "Unknown"
            )

            # Check if this item was extracted using a callback
            callback_name = (
                item.metadata_json.get("_callback")
                if item.metadata_json and isinstance(item.metadata_json, dict)
                else None
            )

            if callback_name and callback_name in callbacks_config:
                # Callback item: show fields defined in spider config
                click.echo(f"🔸 [{i}] {callback_name} item")
                click.echo(f"   📅 Scraped: {scraped_date}")
                click.echo(f"   🔗 {item.url}")

                # Get field definitions from spider config
                extract_config = callbacks_config[callback_name].get("extract", {})

                # Collect all fields to display
                fields_to_show = []

                # Fields defined in spider config (in definition order)
                shown_keys = set()
                for field_name in extract_config.keys():
                    if field_name == "title":
                        field_value = item.title
                    elif field_name == "content":
                        field_value = item.content
                    elif field_name == "author":
                        field_value = item.author
                    elif field_name == "published_date":
                        field_value = (
                            item.published_date.isoformat()
                            if item.published_date
                            else None
                        )
                    else:
                        field_value = item.metadata_json.get(field_name)
                    shown_keys.add(field_name)
                    fields_to_show.append((field_name, field_value))

                # Extra metadata_json fields not in extract config
                # (e.g., listing_data passed via iterate: rank, country_code, etc.)
                if item.metadata_json and isinstance(item.metadata_json, dict):
                    for key, value in item.metadata_json.items():
                        if key not in shown_keys and key != "_callback":
                            fields_to_show.append((key, value))

                for field_name, field_value in fields_to_show:
                    # Truncate long values for display
                    if isinstance(field_value, str) and len(field_value) > 100:
                        display_value = field_value[:100] + "..."
                    elif isinstance(field_value, list):
                        if len(field_value) > 3:
                            display_value = f"[{len(field_value)} items]"
                        elif len(str(field_value)) > 100:
                            display_value = str(field_value)[:100] + "...]"
                        else:
                            display_value = field_value
                    else:
                        display_value = field_value
                    click.echo(f"   • {field_name}: {display_value}")
            else:
                # Article item: show standard article fields
                pub_date = (
                    item.published_date.strftime("%Y-%m-%d")
                    if item.published_date
                    else "Unknown"
                )

                click.echo(f"🔸 [{i}] {item.title or 'No Title'}")
                click.echo(f"   📅 Published: {pub_date} | Scraped: {scraped_date}")
                click.echo(f"   🔗 {item.url}")
                if item.author:
                    click.echo(f"   ✍️  {item.author}")
                if item.content:
                    content_preview = item.content[:150].replace("\n", " ").strip()
                    if len(item.content) > 150:
                        content_preview += "..."
                    click.echo(f"   📝 {content_preview}")

            click.echo()
