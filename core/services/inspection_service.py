"""Inspection service - URL inspection."""

from datetime import datetime

from core.services.models import InspectionResult


def inspect_url(
    url: str,
    browser: bool = False,
) -> InspectionResult:
    """Inspect a URL to get page info.

    Args:
        url: URL to inspect.
        browser: Use browser mode for JS-rendered sites.

    Returns:
        InspectionResult with page details.
    """
    from utils.inspector import inspect_page
    from core.config import get_data_dir

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    project = "inspect"
    output_dir = get_data_dir(project) / "inspections" / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    mode = "browser" if browser else "http"

    inspect_page(url, str(output_dir), "auto", True, mode=mode, project=project)

    html_file = output_dir / "page.html"
    selectors_file = output_dir / "selectors.json"

    result = InspectionResult(
        url=url,
        output_dir=str(output_dir),
        inspected_at=datetime.now(),
        js_rendered=browser,
    )

    if html_file.exists():
        result.html_snapshot = html_file.read_text()[:5000]

    if selectors_file.exists():
        import json

        data = json.loads(selectors_file.read_text())
        if isinstance(data, dict):
            result.detected_selectors = list(data.keys()) if data else []
        elif isinstance(data, list):
            result.detected_selectors = data

    return result
