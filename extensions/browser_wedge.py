"""Fail-loud detection for wedged browser crawls (docs/requests/17) — added for Ranu.

When the shared browser service wedges, every request of a CLOUDFLARE/BROWSER
crawl dies as a downloader exception and the crawl still ends "finished" with
0 items — a silent empty success that Pueue banks as completed. The CLI marks
browser-based crawls with the BROWSER_WEDGE_MARKER setting (a file path); at
spider_closed this extension inspects the crawl's stats and writes the marker
when the wedge signature is present: ZERO downloader responses and at least
one downloader exception (nothing loaded, and the browser path was throwing).
cli/crawl.py turns the marker into a non-zero exit so the crawl shows as
failed and is retryable.

A legitimately-empty re-crawl (DeltaFetch filters every request) writes no
marker: filtered requests produce no downloader exceptions.
"""

import json
import os

from scrapy import signals


class BrowserWedgeDetector:
    """Write BROWSER_WEDGE_MARKER when a browser crawl ends all-exception."""

    def __init__(self, crawler, marker):
        self.crawler = crawler
        self.marker = marker

    @classmethod
    def from_crawler(cls, crawler):
        marker = crawler.settings.get("BROWSER_WEDGE_MARKER")
        ext = cls(crawler, marker)
        # No marker path = not a browser crawl (the CLI only sets it for
        # CLOUDFLARE/BROWSER spiders) — stay inert.
        if marker:
            crawler.signals.connect(ext.spider_opened, signal=signals.spider_opened)
            crawler.signals.connect(ext.spider_closed, signal=signals.spider_closed)
        return ext

    def spider_opened(self, spider):
        # A stale marker from a previous wedged run must not fail THIS run.
        try:
            os.remove(self.marker)
        except OSError:
            pass

    def spider_closed(self, spider):
        stats = self.crawler.stats.get_stats()
        responses = stats.get("downloader/response_count", 0)
        exceptions = stats.get("downloader/exception_count", 0)
        # ponytail: strict zero-response signature — a partial wedge (some
        # responses, then death) is not detected; upgrade path is an
        # exception-ratio threshold.
        if responses == 0 and exceptions > 0:
            data = {
                "spider": getattr(spider, "spider_name", spider.name),
                "responses": responses,
                "exceptions": exceptions,
                "items": stats.get("item_scraped_count", 0),
            }
            try:
                with open(self.marker, "w") as fh:
                    json.dump(data, fh)
            except OSError as e:  # never let wedge detection break a crawl
                spider.logger.warning(f"[wedge] could not write marker: {e}")
