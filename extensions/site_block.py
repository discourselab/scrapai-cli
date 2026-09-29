"""Stop a crawl that the site is blocking (docs/requests/29).

Getting blocked is the one failure a crawl cannot recover from: every further
request to a site that is refusing us makes the block likelier to stick. This
downloader middleware keeps a rolling window over the last 100 downloader
attempts and stops the crawl when 60 of them are blocks:

- SiteBlockedError — a page still challenged right after a fresh browser
  re-verify (handlers/cloudflare_handler.py). Never retried in-crawl, so
  every one is final.
- HTTP 429 — every attempt, retried or not, once the proxy escalation has
  nothing left to try. The middleware sits next to the downloader (above
  RetryMiddleware at 550 and SmartProxyMiddleware at 350). Counting only the
  429s left after retries cannot work in an attempt window: with Scrapy's
  default two retries each such 429 costs three attempts, so even a total
  block peaks at about 36 of 100 and never stops the crawl.

  A direct 429 while SmartProxyMiddleware still has a proxy to escalate to
  does not count: it reaches the proxy only after RetryMiddleware has given
  up, so counting it would stop the crawl before the proxy was ever tried.
  A 429 counts when the request already went through the proxy, or when no
  proxy is available.

  In a browser crawl the Cloudflare handler reports every page as 200, so
  429s never show; only pages it recognises as challenged (SiteBlockedError)
  count there.

Not counted: 403 (healthy crawls hit dense runs of 403 on login-only
sections), transport failures (no response at all) and browser-service
errors (a local fault, not the site).

On the stop, no further request is sent — including those already waiting
in the downloader — and downloads in flight finish. The CLI sets
SITE_BLOCK_MARKER; the marker written at close turns into exit code 4.
Without it (a plain `scrapy crawl`) the crawl still stops.

Every blocked page is also counted in the crawl stats (blocked/site_blocked,
blocked/http_429), so blocks below the threshold are never silent.
"""

import json
import logging
import os
from collections import Counter, deque

from scrapy import signals
from scrapy.exceptions import IgnoreRequest
from scrapy.utils.defer import deferred_from_coro

from handlers.cloudflare_handler import SiteBlockedError
from middlewares import SmartProxyMiddleware

logger = logging.getLogger(__name__)

BLOCK_WINDOW = 100  # downloader attempts
BLOCK_THRESHOLD = 60  # blocks within the window
CLOSE_REASON = "site_blocked"


class SiteBlockGuard:
    """Stop the crawl when the site blocks 60 of the last 100 attempts."""

    def __init__(self, crawler, marker=None):
        self.crawler = crawler
        self.marker = marker
        self.attempts = 0  # downloader attempts seen so far
        self.recent = deque()  # (attempt index, kind) of each recent block
        self.tripped = False
        self._closing = None
        self._smart_proxy = False  # False = not looked up yet
        self.trip_counts = {}  # window counts by kind, at the stop
        self.trip_window = BLOCK_WINDOW  # attempts that window covered

    @classmethod
    def from_crawler(cls, crawler):
        guard = cls(crawler, crawler.settings.get("SITE_BLOCK_MARKER"))
        # Bound methods, kept alive by the middleware: Scrapy holds signal
        # receivers weakly, so a lambda would be collected and never fire.
        crawler.signals.connect(
            guard.request_left_downloader, signal=signals.request_left_downloader
        )
        crawler.signals.connect(guard.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(guard.spider_closed, signal=signals.spider_closed)
        return guard

    def spider_opened(self, spider):
        # A stale marker from an earlier run must not fail THIS run.
        if self.marker:
            try:
                os.remove(self.marker)
            except OSError:
                pass

    def request_left_downloader(self, request, spider):
        self.attempts += 1

    def process_request(self, request):
        if self.tripped:
            raise IgnoreRequest("crawl stopped: the site is blocking it")
        return None

    def process_response(self, request, response):
        if response.status == 429 and not self._proxy_still_to_try(request):
            self._record("http_429", request, "HTTP 429 Too Many Requests")
        return response

    def _proxy_still_to_try(self, request):
        """True when this 429 went direct and SmartProxyMiddleware has a proxy
        it will escalate to — read from its own state, never changed here."""
        if self._smart_proxy is False:
            middlewares = getattr(
                getattr(self.crawler.engine.downloader, "middleware", None),
                "middlewares",
                (),
            )
            self._smart_proxy = next(
                (m for m in middlewares if isinstance(m, SmartProxyMiddleware)), None
            )
        proxy = self._smart_proxy
        return bool(
            proxy
            and proxy.proxy_available
            # A proxy declared dead (where SmartProxyMiddleware tracks that)
            # will not be tried: its direct 429s count.
            and not getattr(proxy, "proxy_dead", False)
            and not request.meta.get("proxy")
        )

    def process_exception(self, request, exception):
        if isinstance(exception, SiteBlockedError):
            self._record("site_blocked", request, "still challenged after re-verify")
        return None

    def _record(self, kind, request, reason):
        self.crawler.stats.inc_value(f"blocked/{kind}")
        logger.warning(f"[site-block] {request.url}: {reason}")
        self.recent.append((self.attempts, kind))
        while self.recent and self.recent[0][0] <= self.attempts - BLOCK_WINDOW:
            self.recent.popleft()
        if not self.tripped and len(self.recent) >= BLOCK_THRESHOLD:
            self._trip()

    def window_counts(self):
        return dict(Counter(kind for _, kind in self.recent))

    def _trip(self):
        self.tripped = True
        # The window as it stood at the stop, not after in-flight downloads.
        self.trip_counts = self.window_counts()
        self.trip_window = min(self.attempts, BLOCK_WINDOW)
        logger.error(
            f"[site-block] {len(self.recent)} of the last {self.trip_window} "
            f"downloads were blocked {self.trip_counts} — stopping the crawl to "
            "protect access to the site"
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
                dfd.errback(IgnoreRequest("crawl stopped before sending"))

    def spider_closed(self, spider):
        if not (self.tripped and self.marker):
            return
        stats = self.crawler.stats.get_stats()
        data = {
            "spider": getattr(spider, "spider_name", spider.name),
            "window": self.trip_window,
            "window_counts": self.trip_counts,
            "totals": {
                "site_blocked": stats.get("blocked/site_blocked", 0),
                "http_429": stats.get("blocked/http_429", 0),
            },
            "responses": stats.get("downloader/response_count", 0),
            "items": stats.get("item_scraped_count", 0),
        }
        try:
            with open(self.marker, "w") as fh:
                json.dump(data, fh)
        except OSError as e:  # never let the marker break a crawl
            spider.logger.warning(f"[site-block] could not write marker: {e}")
