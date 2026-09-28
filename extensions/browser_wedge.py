"""Fail-loud detection for wedged browser crawls (docs/requests/17).

When the shared browser service wedges, the requests of a CLOUDFLARE/BROWSER
crawl die as downloader exceptions and the crawl still ends "finished" — a
silent empty or partial success that Pueue banks as completed. The CLI marks
browser-based crawls with the BROWSER_WEDGE_MARKER setting (a file path); this
downloader middleware writes the marker when it sees a wedge, and cli/crawl.py
turns the marker into exit code 3.

Two signatures, both counting browser-service errors only (see
is_browser_service_error). What does not count: a page still challenged after
a re-verify, a transport error on the HTTP fetch, and a verify the service
reports as the site's doing (a challenge the browser could not pass, or a
site-side navigation error such as DNS, a refused connection or TLS). A
navigation timeout still counts: the service cannot tell a hung browser from a
slow site.

- Partial wedge, mid-crawl: 20 or more of the last 100 downloader attempts
  failed in the browser service. The crawl is stopped at once: no further
  requests are sent, downloads already in flight finish.
- Total wedge, at close: zero downloader responses and at least one
  browser-service error — catches crawls too small to reach the window.

A legitimately empty re-crawl (DeltaFetch filters every request) writes no
marker: filtered requests never reach the downloader.
"""

import concurrent.futures
import json
import logging
import os

from scrapy import signals
from scrapy.exceptions import IgnoreRequest, NotConfigured
from scrapy.utils.defer import deferred_from_coro

logger = logging.getLogger(__name__)

WEDGE_WINDOW = 100  # downloader attempts
WEDGE_THRESHOLD = 20  # browser-service errors within the window
CLOSE_REASON = "browser_wedge"
ATTEMPT_KEY = "browser_wedge_attempt"  # request.meta: attempt index


def is_browser_service_error(exc):
    """True for a failure of the shared browser service, and nothing else.

    The Cloudflare handler raises these with "browser service" in the message
    (unreachable, failed to verify). The other one is the TimeoutError from
    CloudflareDownloadHandler._run_async when a browser operation exceeds its
    300 s budget — matched by exact type (the builtin, and
    concurrent.futures.TimeoutError, a separate class before Python 3.11), so
    subclasses raised by other libraries do not count. The handler's block,
    transport and site-refused errors never say "browser service".
    """
    if type(exc) in (TimeoutError, concurrent.futures.TimeoutError):
        return True
    return "browser service" in str(exc).lower()


class BrowserWedgeDetector:
    """Stop a browser crawl whose browser service is failing; leave a marker."""

    def __init__(self, crawler, marker):
        self.crawler = crawler
        self.marker = marker
        self.attempts = 0  # downloader attempts seen so far
        self.recent = []  # attempt index of each recent service error
        self.service_errors = 0
        self.tripped = False
        self.window_errors = 0  # errors in the window when it tripped
        self.window_seen = WEDGE_WINDOW  # attempts that window covered
        self._closing = None

    @classmethod
    def from_crawler(cls, crawler):
        marker = crawler.settings.get("BROWSER_WEDGE_MARKER")
        # No marker path = not a browser crawl (the CLI only sets it for
        # CLOUDFLARE/BROWSER spiders) — Scrapy drops the middleware.
        if not marker:
            raise NotConfigured("BROWSER_WEDGE_MARKER not set")
        mw = cls(crawler, marker)
        # Bound methods, kept alive by the middleware: Scrapy holds signal
        # receivers weakly, so a lambda would be collected and never fire.
        crawler.signals.connect(mw.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(mw.spider_closed, signal=signals.spider_closed)
        crawler.signals.connect(
            mw.request_left_downloader, signal=signals.request_left_downloader
        )
        return mw

    def spider_opened(self, spider):
        # A stale marker from a previous wedged run must not fail THIS run.
        try:
            os.remove(self.marker)
        except OSError:
            pass

    def request_left_downloader(self, request, spider):
        self.attempts += 1
        # Stamp the attempt: its exception reaches process_exception later
        # (after other attempts may have left), and must count where it was.
        request.meta[ATTEMPT_KEY] = self.attempts

    def process_request(self, request):
        if self.tripped:
            raise IgnoreRequest("browser crawl stopped: browser service wedged")
        return None

    def process_exception(self, request, exception):
        if is_browser_service_error(exception):
            self.service_errors += 1
            self.crawler.stats.inc_value("browser_wedge/service_errors")
            self.recent.append(request.meta.get(ATTEMPT_KEY, self.attempts))
            oldest = self.attempts - WEDGE_WINDOW
            self.recent = [i for i in self.recent if i > oldest]
            if not self.tripped and len(self.recent) >= WEDGE_THRESHOLD:
                self._trip()
        return None

    def _trip(self):
        self.tripped = True
        self.window_errors = len(self.recent)
        self.window_seen = min(self.attempts, WEDGE_WINDOW)
        logger.error(
            f"[wedge] {self.window_errors} of the last {self.window_seen} "
            "downloads failed in the browser service — stopping the crawl"
        )
        engine = self.crawler.engine
        self._closing = deferred_from_coro(
            engine.close_spider_async(reason=CLOSE_REASON)
        )
        # Requests already handed to the downloader wait in its per-slot
        # queues; drop them rather than send them. Downloads in flight finish.
        for slot in list(getattr(engine.downloader, "slots", {}).values()):
            while slot.queue:
                _request, dfd = slot.queue.popleft()
                dfd.errback(IgnoreRequest("browser crawl stopped before sending"))

    def spider_closed(self, spider):
        stats = self.crawler.stats.get_stats()
        responses = stats.get("downloader/response_count", 0)
        total = responses == 0 and self.service_errors > 0
        if not (self.tripped or total):
            return
        data = {
            "spider": getattr(spider, "spider_name", spider.name),
            "kind": "total" if total else "partial",
            "stopped": self.tripped,
            "responses": responses,
            "exceptions": stats.get("downloader/exception_count", 0),
            "service_errors": self.service_errors,
            "window_errors": self.window_errors,
            "window": self.window_seen,
            "items": stats.get("item_scraped_count", 0),
        }
        try:
            with open(self.marker, "w") as fh:
                json.dump(data, fh)
        except OSError as e:  # never let wedge detection break a crawl
            spider.logger.warning(f"[wedge] could not write marker: {e}")
