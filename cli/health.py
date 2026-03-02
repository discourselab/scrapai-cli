"""Health check command - test spiders and generate reports for broken ones."""

import click
import subprocess
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

from core.db import get_db
from core.models import Spider


@click.command()
@click.option(
    "--project",
    "-p",
    required=True,
    help="Project name (required)",
)
@click.option(
    "--report",
    "-r",
    type=click.Path(),
    help="Save report to specific file (default: data/<project>/health/<YYYYMMDD>/report.md)",
)
@click.option(
    "--limit",
    "-l",
    type=int,
    default=5,
    help="Number of items to test per spider (default: 5)",
)
@click.option(
    "--min-content-length",
    type=int,
    default=50,
    help="Minimum content length to consider extraction successful (default: 50)",
)
def health(
    project: str,
    report: Optional[str],
    limit: int,
    min_content_length: int,
):
    """
    Test all spiders in a project and generate reports for broken ones.

    Tests all spiders in a project with --limit flag, checks if extraction
    is working, and generates a report for the coding agent.

    Examples:
        ./scrapai health --project news
        ./scrapai health --project news --report custom-report.md
        ./scrapai health --project news --limit 10
    """
    click.echo(f"\n{'='*60}")
    click.echo(f"Spider Health Check - Project: {project}")
    click.echo(f"{'='*60}\n")

    # Get all spiders in project
    db = next(get_db())
    try:
        spiders = (
            db.query(Spider)
            .filter(Spider.project == project, Spider.active == True)  # noqa: E712
            .order_by(Spider.name)
            .all()
        )

        if not spiders:
            click.echo(f"❌ No active spiders found in project '{project}'", err=True)
            sys.exit(1)

        click.echo(f"Testing {len(spiders)} spider(s)...\n")

        # Run tests
        results = []
        for spider in spiders:
            result = _test_spider(spider.name, project, limit, min_content_length)
            results.append(result)
            _print_result(result)

        # Summary
        passed = sum(1 for r in results if r["status"] == "passed")
        failed = len(results) - passed

        click.echo(f"\n{'='*60}")
        click.echo("Summary")
        click.echo(f"{'='*60}")
        click.echo(f"Total:  {len(results)}")
        click.echo(f"Passed: {passed} ✅")
        click.echo(f"Failed: {failed} ❌")

        # Generate report
        report_path = _generate_report(results, project, report)
        if report_path:
            click.echo(f"\nReport saved to: {report_path}")

        # Exit code: 0 if all passed, 1 if any failed
        sys.exit(0 if failed == 0 else 1)

    finally:
        db.close()


def _test_spider(
    spider_name: str, project: str, limit: int, min_content_length: int
) -> Dict:
    """Test a single spider and return results."""
    result = {
        "spider": spider_name,
        "status": "unknown",
        "items_count": 0,
        "error": None,
        "sample_item": None,
        "problem": None,
    }

    # Create temp output file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_file = Path(f"/tmp/{spider_name}_health_{timestamp}.jsonl")

    try:
        # Run crawl with limit
        cmd = [
            "./scrapai",
            "crawl",
            spider_name,
            "--project",
            project,
            "--limit",
            str(limit),
        ]

        # Run command
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
        )

        # Check if any items were scraped by looking at the database
        # (crawl saves to DB by default)
        from core.db import get_db
        from core.models import ScrapedItem

        db = next(get_db())
        try:
            items = (
                db.query(ScrapedItem)
                .filter(
                    ScrapedItem.spider_name == spider_name,
                    ScrapedItem.project == project,
                )
                .order_by(ScrapedItem.scraped_at.desc())
                .limit(limit)
                .all()
            )

            result["items_count"] = len(items)

            if len(items) < 3:
                # Crawling broken - not finding enough items
                result["status"] = "failed"
                result["problem"] = "crawling"
                result["error"] = (
                    f"Only {len(items)} items found (expected {limit}). "
                    "Spider may not be finding articles."
                )
            else:
                # Check if extraction is working
                sample = items[0]
                result["sample_item"] = {
                    "title": sample.title,
                    "content": sample.content[:100] if sample.content else "",
                    "author": sample.author,
                    "url": sample.url,
                    "date": (
                        sample.published_date.isoformat()
                        if sample.published_date
                        else None
                    ),
                }

                # Check content length
                content_length = len(sample.content) if sample.content else 0
                if content_length < min_content_length:
                    result["status"] = "failed"
                    result["problem"] = "extraction"
                    result["error"] = (
                        f"Content too short ({content_length} chars). "
                        "Extraction selectors may be broken."
                    )
                else:
                    result["status"] = "passed"

        finally:
            db.close()

    except Exception as e:
        result["status"] = "failed"
        result["problem"] = "error"
        result["error"] = str(e)
    finally:
        # Cleanup temp file
        if temp_file.exists():
            temp_file.unlink()

    return result


def _print_result(result: Dict):
    """Print test result to console."""
    status_icon = "✅" if result["status"] == "passed" else "❌"
    spider = result["spider"]

    if result["status"] == "passed":
        click.echo(f"{status_icon} {spider:20} {result['items_count']} items, extraction OK")
    else:
        problem = result["problem"].upper() if result["problem"] else "ERROR"
        click.echo(
            f"{status_icon} {spider:20} {result['items_count']} items, {problem} BROKEN"
        )


def _generate_report(
    results: List[Dict], project: str, custom_path: Optional[str]
) -> Optional[Path]:
    """Generate markdown report for failed spiders."""
    failed = [r for r in results if r["status"] == "failed"]
    passed = [r for r in results if r["status"] == "passed"]

    if not results:
        return None

    # Determine report path
    if custom_path:
        report_path = Path(custom_path)
    else:
        from core.config import get_data_dir

        date = datetime.now().strftime("%Y%m%d")
        report_path = get_data_dir(project) / "health" / date / "report.md"

    report_path.parent.mkdir(parents=True, exist_ok=True)

    # Generate report
    lines = [
        f"# Spider Health Report - {project}",
        "",
        f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Total:** {len(results)} spiders",
        f"**Passed:** {len(passed)}",
        f"**Failed:** {len(failed)}",
        "",
    ]

    if failed:
        lines.extend(["## Failed Spiders", ""])
        for result in failed:
            lines.extend(_format_failed_spider(result))

    if passed:
        lines.extend(["## Passed Spiders", ""])
        for result in passed:
            lines.append(f"- {result['spider']} ({result['items_count']} items)")
        lines.append("")

    # Write report
    report_path.write_text("\n".join(lines))
    return report_path


def _format_failed_spider(result: Dict) -> List[str]:
    """Format a failed spider for the report."""
    lines = [
        f"### {result['spider']} ({result['problem'].upper()} BROKEN)",
        "",
        f"- **Items found:** {result['items_count']}",
        f"- **Problem:** {result['error']}",
    ]

    if result["sample_item"]:
        lines.extend(
            [
                "- **Sample output:**",
                "  ```json",
                "  {",
                f'    "title": "{result["sample_item"]["title"]}",',
                f'    "content": "{result["sample_item"]["content"]}...",',
                f'    "author": "{result["sample_item"]["author"]}",',
                f'    "date": "{result["sample_item"]["date"]}",',
                f'    "url": "{result["sample_item"]["url"]}"',
                "  }",
                "  ```",
            ]
        )

    # Add fix instructions
    if result["problem"] == "extraction":
        lines.extend(
            [
                "- **Fix needed:** Update CSS selectors for content extraction",
                f"- **Test URL:** {result['sample_item']['url'] if result['sample_item'] else 'N/A'}",
            ]
        )
    elif result["problem"] == "crawling":
        lines.extend(
            [
                "- **Fix needed:** Update crawling rules (URL patterns, start URLs, or allowed domains)",
                "- **Action:** Re-analyze site structure and update spider config",
            ]
        )

    lines.append("")
    return lines
