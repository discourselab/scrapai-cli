# This file is part of nodriver-cf-verify.
# Copyright (c) 2025 OMEGASTRUX
#
# nodriver-cf-verify is free software: you can redistribute it and/or
# modify it under the terms of the GNU Affero General Public License
# as published by the Free Software Foundation, either version 3 of
# the License, or (at your option) any later version.
#
# nodriver-cf-verify is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with nodriver-cf-verify. If not, see <https://www.gnu.org/licenses/>.



import asyncio
import random
from datetime import datetime
from typing import Optional, Any, Union


class CFLibUtil:
    def __init__(self):
        """
        Initialize CFLibUtil for nodriver and zendriver support.
        Unfortunately this causes warnings with types.
        """

        try:
            import nodriver
        except ImportError:
            nodriver = None

        try:
            import zendriver
        except ImportError:
            zendriver = None

        if not nodriver and not zendriver:
            raise ImportError("You need nodriver or zendriver installed to use this script.")

        if nodriver and zendriver:
            self.Browser = Union[nodriver.Browser, zendriver.Browser]
            self.Tab = Union[nodriver.Tab, zendriver.Tab]
            self.Element = Union[nodriver.Element, zendriver.Element]
            return self._set_globally()

        if nodriver:
            self.Browser = nodriver.Browser
            self.Tab = nodriver.Tab
            self.Element = nodriver.Element

        if zendriver:
            self.Browser = zendriver.Browser
            self.Tab = zendriver.Tab
            self.Element = zendriver.Element

        self._set_globally()

    def _set_globally(self):
        global Browser, Tab, Element
        Browser, Tab, Element = self.Browser, self.Tab, self.Element

# Try to load available web driver libraries and set types globally
CFLibUtil()


class CFLogger:
    def __init__(self, _class_name: str, _debug: bool = False) -> None:
        self.debug: bool = _debug
        self.class_name: str = _class_name

    async def log(self, _message: str) -> None:
        """
        Simple logger for CFVerify
        """

        if not self.debug:
            return

        print(f"({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) [{self.class_name}]: {_message}")


class CFUtil:
    def __init__(self, _browser_tab: Tab, _debug = False) -> None:
        self.debug: bool = _debug
        self.browser_tab: Tab = _browser_tab
        self.cf_logger: CFLogger = CFLogger(_class_name = self.__class__.__name__, _debug = self.debug)

    async def create_instance_id(self, _max_retries: int = 10) -> Optional[str]:
        """
        CFUtil method for creating the instance_id from target_id and url.
        """

        for retry_count in range(1, _max_retries + 1):
            target_id: Optional[str] = self.browser_tab.target.target_id
            target_url: Optional[str] = self.browser_tab.target.url

            # That's for nodriver support
            if "://" in target_url:
                target_url = target_url.split("/")[2]

            if not target_id or not target_url:
                await asyncio.sleep(0.05)
                continue

            # instance_id: Optional[str] = f"{target_id[-5:]}-{target_url.split('/')[2]}"
            instance_id: Optional[str] = f"{target_id[-5:]}-{target_url}"
            await self.cf_logger.log(f"Created instance_id: {instance_id}")
            return instance_id

        await self.cf_logger.log(f"instance_id could not be created.")

    async def run_js(self, javascript: str, return_value: bool = True) -> Any:
        result: Any = await self.browser_tab.evaluate(expression = javascript)

        if not return_value:
            return

        if not isinstance(result, list):
            return result

        results = []
        for value in result:
            if not isinstance(value, dict):
                # For zendriver support. zendriver doesnt return objects {type, value}
                results.append(value)
                continue

            # For nodriver support. nodriver returns objects {type, value}
            results.append(value['value'])

        return results

class CFHelper:
    def __init__(self, _browser_tab: Tab, _debug: bool = False) -> None:
        self.debug: bool = _debug
        self.browser_tab: Tab = _browser_tab

        self.cf_util: CFUtil = CFUtil(self.browser_tab, _debug = self.debug)
        self.cf_logger: CFLogger = CFLogger(_class_name = self.__class__.__name__, _debug = self.debug)

    async def is_cloudflare_presented(self, _max_retries: int = 5, _interval_between_retries: float = 0.1) -> bool:
        """
        Checks if Cloudflare challenge script is present on the page.
        """

        obv_things: list[str] = ["challenges.cloudflare.com", "cdn-cgi/challenge-platform", "turnstile/v0/api.js"]
        urls: list[str] = []

        for i in range(_max_retries):
            for i in range(5):
                try:
                    if "turnstile" in await self.browser_tab.evaluate("document.title"):
                        return True

                    # Using javascript instead if find_all, because it's a lot faster than method used in nodriver
                    urls: list[str] = await self.cf_util.run_js("[...document.querySelectorAll('script[src]')].map(script => script.src)", return_value = True)

                    if not urls:
                        continue

                    break

                except Exception as e:
                    await self.cf_logger.log(f"Error occured while fetching urls from site: {e}")

                await asyncio.sleep(0.1)

            if len(urls) == 0:
                await self.cf_logger.log(f"No urls were fetched from site.")
                continue

            for thing in obv_things:
                for url in urls:
                    if thing in url:
                        return True

            await asyncio.sleep(delay = _interval_between_retries)

        return False

    async def find_cloudflare_iframe(self) -> Optional[Element]:
        """
        Searches for an iframe likely related to Cloudflare challenge.
        Returns the iframe element if found, otherwise None.
        """
        
        try:
            iframes: list[Element] = [iframe for iframe in await self.browser_tab.find_all("iframe") if iframe.attrs.get("src")]

            for iframe in iframes:
                iframe_id: str = iframe.attrs.get("id", "").lower()
                iframe_class: str = iframe.attrs.get("class", "").lower()

                if "cf-" in iframe_id or "turnstile" in iframe_id or "cf-" in iframe_class:
                    await self.cf_logger.log(
                        f"Found potential Cloudflare iframe with {'id=' + iframe_id if iframe_id else ''}"
                        f"{' and ' if iframe_id and iframe_class else ''}"
                        f"{'class=' + iframe_class if iframe_class else ''}"
                    )
                    return iframe

        except Exception as e:
            await self.cf_logger.log(f"Error occurred: {e}")


class CFHumanBehavior:
    """
    Adds human-like patterns to avoid bot detection.
    Random delays, mouse movements, scrolling, and hover patterns.
    """

    def __init__(self, _browser_tab: Tab, _debug: bool = False) -> None:
        self.browser_tab: Tab = _browser_tab
        self.debug: bool = _debug
        self.cf_logger: CFLogger = CFLogger(_class_name=self.__class__.__name__, _debug=self.debug)

    async def random_delay(self, min_sec: float = 0.5, max_sec: float = 2.0) -> None:
        """Random delay to mimic human reaction time"""
        delay = random.uniform(min_sec, max_sec)
        await self.cf_logger.log(f"Random delay: {delay:.2f}s")
        await asyncio.sleep(delay)

    async def random_scroll(self) -> None:
        """Random small scroll movements like humans adjusting view"""
        try:
            # Small random scroll (humans don't sit perfectly still)
            scroll_x = random.randint(-10, 10)
            scroll_y = random.randint(50, 200)
            await self.browser_tab.evaluate(f"window.scrollBy({scroll_x}, {scroll_y})")
            await self.cf_logger.log(f"Random scroll: ({scroll_x}, {scroll_y})")
            await self.random_delay(0.3, 0.8)

            # Sometimes scroll back a bit (humans browse around)
            if random.random() > 0.5:
                scroll_back = random.randint(-50, -20)
                await self.browser_tab.evaluate(f"window.scrollBy(0, {scroll_back})")
                await self.random_delay(0.2, 0.5)
        except Exception as e:
            await self.cf_logger.log(f"Error during random scroll: {e}")

    async def viewport_jitter(self) -> None:
        """Tiny viewport movements like humans adjusting window"""
        try:
            jitter_x = random.randint(-3, 3)
            jitter_y = random.randint(-3, 3)
            await self.browser_tab.evaluate(f"window.scrollBy({jitter_x}, {jitter_y})")
            await self.cf_logger.log(f"Viewport jitter: ({jitter_x}, {jitter_y})")
        except Exception as e:
            await self.cf_logger.log(f"Error during viewport jitter: {e}")

    async def mouse_move_to_element(self, element: Element) -> None:
        """Move mouse to element with human-like pattern"""
        try:
            # Get element position
            await self.cf_logger.log("Moving mouse to element position")

            # Add small random offset (humans don't click exact center)
            offset_x = random.randint(-5, 5)
            offset_y = random.randint(-5, 5)

            # Move with slight randomness
            await element.mouse_move()
            await self.cf_logger.log(f"Mouse moved to element (offset: {offset_x}, {offset_y})")

            # Hover pause (humans pause before clicking)
            hover_time = random.uniform(0.3, 0.9)
            await self.cf_logger.log(f"Hovering for {hover_time:.2f}s before click")
            await asyncio.sleep(hover_time)

        except Exception as e:
            await self.cf_logger.log(f"Error during mouse movement: {e}")

    async def pre_interaction_behavior(self) -> None:
        """Simulate human behavior before interacting with page"""
        await self.cf_logger.log("Simulating human pre-interaction behavior")

        # Random initial delay (human reading/observing page)
        await self.random_delay(1.0, 2.5)

        # Sometimes do a small scroll (humans browse before clicking)
        if random.random() > 0.3:
            await self.random_scroll()

        # Viewport micro-adjustment
        await self.viewport_jitter()

        # Final pause before interaction
        await self.random_delay(0.5, 1.2)


class CFVerify:
    def __init__(self, _browser_tab: Tab, _debug: bool = False) -> None:
        """
        Initializes CFVerify with the given browser tab and debug flag.
        Raises ValueError if arguments are of incorrect types.
        """

        if not isinstance(_browser_tab, Tab):
            raise ValueError(f"_browser_tab parameter must be an instance of Tab.")

        if not isinstance(_debug, bool):
            raise ValueError(f"_debug parameter must be a bool.")

        self.debug: bool = _debug
        self.browser_tab: Tab = _browser_tab
        self.instance_id: Optional[str] = None

        self.cf_util: CFUtil = CFUtil(_browser_tab = self.browser_tab, _debug = self.debug)
        self.cf_helper: CFHelper = CFHelper(_browser_tab = self.browser_tab, _debug = self.debug)
        self.cf_logger: CFLogger = CFLogger(self.__class__.__name__, _debug = self.debug)
        self.cf_human: CFHumanBehavior = CFHumanBehavior(_browser_tab = self.browser_tab, _debug = self.debug)

    async def log(self, message: str) -> None:
        """
        Logs a message prefixed by the instance ID.
        If the instance ID is not set, it attempts to create it before logging.
        """

        if not self.instance_id:
            self.instance_id = await self.cf_util.create_instance_id()

        await self.cf_logger.log(f"<{self.instance_id}>: {message}")

    async def verify(self, _max_retries = 10, _interval_between_retries = 1, _reload_page_after_n_retries = 0) -> bool:
        """
        Attempts to verify Cloudflare challenge by retrying up to _max_retries times.
        Optionally reloads the page every _reload_page_after_n_retries attempts.

        Uses human-like patterns: random delays, mouse movements, scrolling.
        """

        await self.log("Verifying cloudflare has started (with human-like patterns).")

        # Initial human behavior (observe page like a real user)
        await self.cf_human.pre_interaction_behavior()

        for retry_count in range(1, _max_retries + 1):
            await self.log(f"Trying to verify cloudflare. Attempt {retry_count} of {_max_retries}.")

            # Random delay instead of fixed (humans have varying reaction times)
            min_delay = max(0.5, _interval_between_retries - 0.5)
            max_delay = _interval_between_retries + 1.0
            await self.cf_human.random_delay(min_delay, max_delay)

            if retry_count < _max_retries and _reload_page_after_n_retries > 0 and retry_count % _reload_page_after_n_retries == 0:
                await self.log(f"Reloading page... Attempt {retry_count} of {_max_retries}, reload interval {_reload_page_after_n_retries}.")
                await self.browser_tab.reload()
                # Human-like delay after reload (humans wait for page to load)
                await self.cf_human.random_delay(2.0, 4.0)
                continue

            if not await self.cf_helper.is_cloudflare_presented():
                await self.log(f"Cloudflare is not presented on site. No verify needed.")
                return True

            iframe: Optional[Element] = await self.cf_helper.find_cloudflare_iframe()

            if not iframe:
                await self.log("No cloudflare iframe found.")

                if not await self.cf_helper.is_cloudflare_presented():
                    await self.log("Cloudflare has been verified successfully (no iframe required).")
                    return True

                # Random delay before retry
                await self.cf_human.random_delay(0.5, 1.5)
                continue

            try:
                # Human-like behavior before clicking
                await self.log("Simulating human interaction before clicking iframe...")

                # Small viewport adjustment (humans fidget)
                await self.cf_human.viewport_jitter()

                # Move mouse to element with hover (humans don't instant-click)
                await self.cf_human.mouse_move_to_element(iframe)

                # Click the iframe
                await iframe.mouse_click()
                await self.log("Cloudflare iframe has been clicked (human-like).")

                # Random delay after click (humans wait to see result)
                await self.cf_human.random_delay(1.5, 3.0)

            except Exception as e:
                await self.log(f"Error while clicking iframe: {e}")

                if "could not find position for" in str(e):
                    await self.log(f"Cloudflare iframe could not load properly.")
                    await self.cf_human.random_delay(0.5, 1.5)
                    continue

                if not await self.cf_helper.is_cloudflare_presented():
                    await self.log("Cloudflare has been verified successfully despite error.")
                    return True

        if await self.cf_helper.is_cloudflare_presented():
            await self.log("Cloudflare could not be verified for an unknown reason.")
            return False

        await self.log("Cloudflare has been verified successfully (human-like patterns used).")
        return True
