"""Shared mixin for database-driven spiders."""

import json
import logging
import re

logger = logging.getLogger(__name__)


class BaseDBSpiderMixin:
    """Mixin providing shared logic for DatabaseSpider and SitemapDatabaseSpider."""

    def _load_settings_from_db(self, spider_record):
        """Deserialize settings from DB spider record into custom_settings."""
        if not getattr(self, "custom_settings", None):
            self.custom_settings = {}

        if not spider_record.settings:
            return

        for s in spider_record.settings:
            val = s.value
            try:
                val = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                if isinstance(val, str):
                    if val.lower() == "true":
                        val = True
                    elif val.lower() == "false":
                        val = False
                    elif val.isdigit():
                        val = int(val)
            self.custom_settings[s.key] = val

    def _setup_cloudflare_handlers(self):
        """Configure Cloudflare or curl_cffi download handlers if enabled."""
        cf_enabled = self.custom_settings.get("CLOUDFLARE_ENABLED", False)
        curl_cffi_enabled = self.custom_settings.get("CURL_CFFI_ENABLED", False)

        if curl_cffi_enabled:
            logger.info(f"curl_cffi TLS impersonation enabled for {self.spider_name}")
            self.custom_settings["DOWNLOAD_HANDLERS"] = {
                "http": "handlers.curl_cffi_handler.CurlCffiDownloadHandler",
                "https": "handlers.curl_cffi_handler.CurlCffiDownloadHandler",
            }
        elif cf_enabled:
            logger.info(f"Cloudflare bypass mode enabled for {self.spider_name}")
            self.custom_settings["DOWNLOAD_HANDLERS"] = {
                "http": "handlers.cloudflare_handler.CloudflareDownloadHandler",
                "https": "handlers.cloudflare_handler.CloudflareDownloadHandler",
            }

    @classmethod
    def _apply_cf_to_crawler(cls, spider, crawler):
        """Apply Cloudflare or curl_cffi handlers to crawler settings after spider init."""
        if hasattr(spider, "custom_settings"):
            cf_enabled = spider.custom_settings.get("CLOUDFLARE_ENABLED", False)
            curl_cffi_enabled = spider.custom_settings.get("CURL_CFFI_ENABLED", False)

            if curl_cffi_enabled:
                logger.info(
                    "[from_crawler] Applying curl_cffi handlers to crawler settings"
                )
                crawler.settings.set(
                    "DOWNLOAD_HANDLERS",
                    {
                        "http": "handlers.curl_cffi_handler.CurlCffiDownloadHandler",
                        "https": "handlers.curl_cffi_handler.CurlCffiDownloadHandler",
                    },
                    priority="spider",
                )
            elif cf_enabled:
                logger.info(
                    "[from_crawler] Applying Cloudflare handlers to crawler settings"
                )
                crawler.settings.set(
                    "DOWNLOAD_HANDLERS",
                    {
                        "http": "handlers.cloudflare_handler.CloudflareDownloadHandler",
                        "https": "handlers.cloudflare_handler.CloudflareDownloadHandler",
                    },
                    priority="spider",
                )

        spider._item_limit = crawler.settings.getint("CLOSESPIDER_ITEMCOUNT", 0)
        if spider._item_limit:
            logger.info(f"Item limit set to {spider._item_limit}")

    async def _extract_article(self, response, source_label="database_spider"):
        """Shared article extraction logic."""
        default_strategies = ["newspaper", "trafilatura", "playwright"]

        strategies = self.custom_settings.get("EXTRACTOR_ORDER")
        if isinstance(strategies, str):
            try:
                strategies = json.loads(strategies.replace("'", '"'))
            except Exception:
                strategies = None
        if not isinstance(strategies, list):
            strategies = default_strategies

        logger.info(f"Using strategies: {strategies}")

        custom_selectors = self.custom_settings.get("CUSTOM_SELECTORS")
        if isinstance(custom_selectors, str):
            try:
                custom_selectors = json.loads(custom_selectors.replace("'", '"'))
            except Exception:
                custom_selectors = None

        if custom_selectors:
            logger.info(f"Using custom selectors: {list(custom_selectors.keys())}")

        from core.extractors import SmartExtractor

        extractor = SmartExtractor(
            strategies=strategies, custom_selectors=custom_selectors
        )

        logger.info(f"Processing {response.url} (Length: {len(response.text)})")
        title_hint = response.css("title::text").get()
        if title_hint:
            logger.info(f"Title tag: {title_hint}")

        include_html = self.settings.getbool("INCLUDE_HTML_IN_OUTPUT", False)

        wait_for_selector = self.custom_settings.get("PLAYWRIGHT_WAIT_SELECTOR")
        wait_delay = self.custom_settings.get("PLAYWRIGHT_DELAY", 0)
        enable_scroll = self.custom_settings.get("INFINITE_SCROLL", False)
        max_scrolls = self.custom_settings.get("MAX_SCROLLS", 5)
        scroll_delay = self.custom_settings.get("SCROLL_DELAY", 1.0)

        if wait_for_selector:
            logger.info(f"Playwright will wait for selector: {wait_for_selector}")
        if wait_delay and float(wait_delay) > 0:
            logger.info(f"Playwright will wait additional {wait_delay} seconds")
        if enable_scroll:
            logger.info(
                f"Infinite scroll enabled: {max_scrolls} scrolls with {scroll_delay}s delay"
            )

        article = await extractor.extract(
            response.url,
            response.text,
            title_hint=title_hint,
            include_html=include_html,
            wait_for_selector=wait_for_selector,
            additional_delay=float(wait_delay) if wait_delay else 0,
            enable_scroll=bool(enable_scroll),
            max_scrolls=int(max_scrolls) if max_scrolls else 5,
            scroll_delay=float(scroll_delay) if scroll_delay else 1.0,
        )

        if article:
            item = article.model_dump()
            item["spider_name"] = self.spider_name
            item["spider_id"] = self.spider_config.id
            item["source"] = source_label

            # Yield item first, let Scrapy's CLOSESPIDER_ITEMCOUNT handle the limit
            yield item

            # Increment counter after yielding (so item can be processed)
            self._items_scraped += 1
        else:
            logger.warning(f"Failed to extract article from {response.url}")

    def _extract_field(self, selector, config):
        """Extract a single field using CSS or XPath selector.

        Args:
            selector: Scrapy Selector object
            config: Dict with 'css' or 'xpath' key, optional 'get_all' flag

        Returns:
            Extracted value (string, list, or None)
        """
        css = config.get("css")
        xpath = config.get("xpath")
        get_all = config.get("get_all", False)

        if css:
            result = selector.css(css)
        elif xpath:
            result = selector.xpath(xpath)
        else:
            return None

        if get_all:
            return result.getall()
        else:
            return result.get()

    def _extract_nested_list(self, selector, config, depth=0, max_depth=3):
        """Extract a list of items with nested field extraction.

        Args:
            selector: Scrapy Selector object
            config: Dict with 'selector' and 'extract' keys
            depth: Current nesting depth
            max_depth: Maximum nesting depth to prevent infinite loops

        Returns:
            List of dicts with extracted fields
        """
        if depth >= max_depth:
            logger.warning(f"Max nesting depth {max_depth} reached, stopping")
            return []

        item_selector = config.get("selector")
        extract_config = config.get("extract", {})

        if not item_selector or not extract_config:
            logger.warning("nested_list requires 'selector' and 'extract' keys")
            return []

        from core.processors import apply_processors

        items = []
        for item_node in selector.css(item_selector):
            item = {}
            for field_name, field_config in extract_config.items():
                # Handle nested_list recursively
                if field_config.get("type") == "nested_list":
                    item[field_name] = self._extract_nested_list(
                        item_node, field_config, depth=depth + 1, max_depth=max_depth
                    )
                else:
                    value = self._extract_field(item_node, field_config)
                    processors = field_config.get("processors", [])
                    if processors:
                        value = apply_processors(value, processors)
                    item[field_name] = value
            items.append(item)

        return items

    async def _extract_ajax_nested_list(self, response, config):
        """Extract nested list from an AJAX endpoint.

        Makes an HTTP POST request to an AJAX URL, parses the HTML response,
        and extracts fields using the same selector system as nested_list.

        Config format:
        {
            "type": "ajax_nested_list",
            "ajax_url": "/wp-admin/admin-ajax.php",  (relative or absolute)
            "ajax_data": {"action": "wpdLoadMoreComments", ...},
            "post_id_css": "video-js::attr(data-parent-post-id)",  (selector to get post ID)
            "response_json_field": "data.comment_list",  (dot-path to HTML in JSON response)
            "selector": "div.wpd-comment",  (CSS selector for each item in response HTML)
            "extract": { ... field configs ... }
        }
        """
        import json as json_module
        from scrapy import Selector
        from core.processors import apply_processors

        ajax_url = config.get("ajax_url", "")
        ajax_data = dict(config.get("ajax_data", {}))
        post_id_css = config.get("post_id_css")
        response_json_field = config.get("response_json_field")
        item_selector = config.get("selector")
        extract_config = config.get("extract", {})

        if not ajax_url or not item_selector or not extract_config:
            logger.warning("ajax_nested_list requires ajax_url, selector, and extract")
            return []

        # Resolve relative URL
        if ajax_url.startswith("/"):
            from urllib.parse import urljoin
            ajax_url = urljoin(response.url, ajax_url)

        # Get post ID if needed
        post_id_regex = config.get("post_id_regex")
        if post_id_css:
            raw_id = response.css(post_id_css).get()
            if raw_id and post_id_regex:
                import re as re_module
                match = re_module.search(post_id_regex, raw_id)
                post_id = match.group(1) if match else raw_id
            else:
                post_id = raw_id
            if post_id:
                # Replace {post_id} placeholder in ajax_url and ajax_data values
                if "{post_id}" in ajax_url:
                    ajax_url = ajax_url.replace("{post_id}", post_id)
                for key, val in ajax_data.items():
                    if isinstance(val, str) and "{post_id}" in val:
                        ajax_data[key] = val.replace("{post_id}", post_id)

        ajax_method = config.get("ajax_method", "POST").upper()
        response_type = config.get("response_type", "json_html")
        ajax_per_page = config.get("ajax_per_page", 0)

        try:
            import curl_cffi.requests as curl_requests
            import asyncio

            loop = asyncio.get_event_loop()

            all_items = []
            page = 1
            while True:
                # Build request params
                request_data = dict(ajax_data)
                if ajax_per_page and ajax_per_page > 0:
                    request_data["per_page"] = str(ajax_per_page)
                    request_data["page"] = str(page)

                # Build the actual URL with query params for GET
                request_url = ajax_url
                if ajax_method == "GET" and request_data:
                    from urllib.parse import urlencode
                    request_url = f"{ajax_url}?{urlencode(request_data)}"

                if ajax_method == "GET":
                    resp = await loop.run_in_executor(
                        None,
                        lambda url=request_url: curl_requests.get(
                            url, impersonate="chrome", timeout=30,
                        ),
                    )
                else:
                    resp = await loop.run_in_executor(
                        None,
                        lambda: curl_requests.post(
                            ajax_url,
                            data=request_data,
                            impersonate="chrome",
                            timeout=30,
                        ),
                    )

                if resp.status_code != 200:
                    if page > 1:
                        break  # Pagination exhausted
                    logger.warning(
                        f"AJAX request failed: {resp.status_code} for {request_url}"
                    )
                    return all_items

                # Handle response based on type
                if response_type == "json_array":
                    # Response is a JSON array of objects (e.g., WP REST API)
                    try:
                        json_data = json_module.loads(resp.text)
                        # Navigate to nested array if response_json_field specified
                        if response_json_field and isinstance(json_data, dict):
                            for key in response_json_field.split("."):
                                json_data = json_data[key]
                        json_items = json_data
                        if not isinstance(json_items, list) or len(json_items) == 0:
                            break
                    except (json_module.JSONDecodeError, KeyError, TypeError):
                        break

                    for json_obj in json_items:
                        item = {}
                        for field_name, field_config in extract_config.items():
                            json_path = field_config.get("json_path")
                            if json_path:
                                # Navigate dot-path in JSON object
                                value = json_obj
                                for key in json_path.split("."):
                                    if isinstance(value, dict):
                                        value = value.get(key)
                                    else:
                                        value = None
                                        break
                                # Strip HTML tags if present
                                if isinstance(value, str) and "<" in value:
                                    import re as re_mod
                                    value = re_mod.sub(r"<[^>]+>", "", value).strip()
                                procs = field_config.get("processors", [])
                                if procs:
                                    value = apply_processors(value, procs)
                                item[field_name] = value
                        all_items.append(item)

                    # Check if we need to paginate
                    if ajax_per_page and ajax_per_page > 0 and len(json_items) >= ajax_per_page:
                        page += 1
                        continue
                    else:
                        break

                elif response_type == "json_object":
                    # Response is a single JSON object — extract fields and return as dict
                    try:
                        json_data = json_module.loads(resp.text)
                        if response_json_field and isinstance(json_data, dict):
                            for key in response_json_field.split("."):
                                json_data = json_data[key]
                        if not isinstance(json_data, dict):
                            break
                    except (json_module.JSONDecodeError, KeyError, TypeError):
                        break

                    item = {}
                    for field_name, field_config in extract_config.items():
                        json_path = field_config.get("json_path")
                        if json_path:
                            value = json_data
                            for key in json_path.split("."):
                                if isinstance(value, dict):
                                    value = value.get(key)
                                elif isinstance(value, list) and key.isdigit():
                                    value = value[int(key)] if int(key) < len(value) else None
                                else:
                                    value = None
                                    break
                            if isinstance(value, str) and "<" in value:
                                import re as re_mod
                                value = re_mod.sub(r"<[^>]+>", "", value).strip()
                            procs = field_config.get("processors", [])
                            if procs:
                                value = apply_processors(value, procs)
                            item[field_name] = value
                    # Return as dict, not list — caller stores directly as field value
                    return item

                else:
                    # response_type == "json_html" (default)
                    html_content = resp.text
                    if response_json_field:
                        try:
                            json_data = json_module.loads(resp.text)
                            for key in response_json_field.split("."):
                                json_data = json_data[key]
                            html_content = json_data
                        except (json_module.JSONDecodeError, KeyError, TypeError) as e:
                            logger.warning(f"Failed to parse AJAX JSON response: {e}")
                            return all_items

                    sel = Selector(text=html_content)
                    for item_node in sel.css(item_selector):
                        item = {}
                        for field_name, field_config in extract_config.items():
                            if field_config.get("type") == "nested_list":
                                item[field_name] = self._extract_nested_list(
                                    item_node, field_config
                                )
                            else:
                                value = self._extract_field(item_node, field_config)
                                procs = field_config.get("processors", [])
                                if procs:
                                    value = apply_processors(value, procs)
                                item[field_name] = value
                        all_items.append(item)
                    break  # No pagination for HTML responses

            # Nest replies under parent comments if configured
            nest_replies = config.get("nest_replies", False)
            if nest_replies and all_items:
                id_field = config.get("comment_id_field") or "comment_id"
                parent_field = config.get("parent_id_field") or "parent_id"
                replies_field = config.get("replies_field") or "replies"

                # Build lookup by comment_id
                by_id = {}
                for item in all_items:
                    cid = item.get(id_field)
                    if cid is not None:
                        by_id[cid] = item
                        item[replies_field] = []

                if not by_id and all_items:
                    logger.debug(
                        f"nest_replies: no '{id_field}' found in items. "
                        f"Available keys: {list(all_items[0].keys())}"
                    )

                # Nest children under parents
                roots = []
                for item in all_items:
                    pid = item.get(parent_field)
                    if pid and pid != 0 and pid in by_id:
                        by_id[pid][replies_field].append(item)
                    else:
                        roots.append(item)

                all_items = roots
                logger.info(
                    f"Nested {len(all_items)} top-level comments "
                    f"(from {len(by_id)} total) from {ajax_url}"
                )
            else:
                logger.info(
                    f"AJAX extracted {len(all_items)} items from {ajax_url}"
                )

            return all_items

        except ImportError:
            logger.warning("curl_cffi not available for AJAX requests")
            return []
        except Exception as e:
            logger.error(f"AJAX extraction failed: {e}")
            return []

    def _get_callback(self, callback_name):
        """Look up a registered callback method by name.

        Args:
            callback_name: Name of the callback (must be registered via setattr)

        Returns:
            The callback method

        Raises:
            AttributeError: If callback is not registered
        """
        callback = getattr(self, callback_name, None)
        if callback is None:
            raise AttributeError(
                f"Callback '{callback_name}' not registered on spider. "
                "Ensure it is defined in the callbacks config."
            )
        return callback

    def _extract_url_context(self, url, url_context_config):
        """Extract fields from a URL using regex patterns.

        Args:
            url: The URL string to extract from
            url_context_config: Dict of {field_name: {"regex": pattern}}

        Returns:
            Dict of extracted field values
        """
        context = {}
        for field_name, field_config in url_context_config.items():
            pattern = field_config.get("regex", "")
            match = re.search(pattern, url)
            if match:
                context[field_name] = match.group(1)
            else:
                context[field_name] = None
        return context

    def _make_callback(self, callback_name, callback_config):
        """Generate a dynamic callback method for custom field extraction.

        Args:
            callback_name: Name of the callback (e.g., 'parse_product')
            callback_config: Dict with 'extract' key containing field definitions,
                           or 'iterate' key for listing→detail page workflows

        Returns:
            Async generator function for Scrapy callback
        """
        iterate_config = callback_config.get("iterate")

        if iterate_config:
            return self._make_iterate_callback(callback_name, callback_config)
        else:
            return self._make_standard_callback(callback_name, callback_config)

    def _make_iterate_callback(self, callback_name, callback_config):
        """Generate a callback that iterates over listing rows and follows detail pages."""

        async def iterate_callback(response):
            from core.processors import apply_processors

            iterate_config = callback_config["iterate"]
            row_selector = iterate_config["selector"]
            follow_config = iterate_config["follow"]
            url_context_config = iterate_config.get("url_context")
            extract_config = callback_config.get("extract") or {}

            # Extract url_context once per page
            url_context = {}
            if url_context_config:
                url_context = self._extract_url_context(
                    response.url, url_context_config
                )

            rows = response.css(row_selector)
            logger.info(
                f"Iterate {callback_name}: found {len(rows)} rows on {response.url}"
            )

            for row in rows:
                # Extract per-row fields
                row_data = {}
                for field_name, field_config in extract_config.items():
                    if field_config.get("type") == "nested_list":
                        value = self._extract_nested_list(row, field_config)
                    else:
                        value = self._extract_field(row, field_config)

                    processors = field_config.get("processors", [])
                    if processors:
                        value = apply_processors(value, processors)

                    row_data[field_name] = value

                # Extract follow URL from row
                follow_url = self._extract_field(row, follow_config["url"])
                if not follow_url:
                    logger.debug(f"Iterate {callback_name}: skipping row without URL")
                    continue

                # Combine row_data + url_context into listing_data
                listing_data = {**row_data, **url_context}

                yield response.follow(
                    follow_url,
                    callback=self._get_callback(follow_config["callback"]),
                    meta={"listing_data": listing_data},
                )

        return iterate_callback

    def _make_standard_callback(self, callback_name, callback_config):
        """Generate a standard callback that extracts fields from a single page."""

        async def standard_callback(response):
            """Generated callback that extracts custom fields and applies processors."""
            from core.processors import apply_processors

            extract_config = callback_config.get("extract") or {}
            if not extract_config:
                logger.warning(
                    f"Callback {callback_name} has no extraction config, skipping"
                )
                return

            # Build the item with custom fields
            item = {
                "url": response.url,
                "spider_name": self.spider_name,
                "spider_id": self.spider_config.id,
                "source": "custom_callback",
                "_callback": callback_name,  # Mark as callback item for pipeline
            }

            # Merge listing_data from iterate parent (if any)
            try:
                listing_data = response.meta.get("listing_data", {})
            except AttributeError:
                listing_data = {}
            item.update(listing_data)

            # Extract all custom fields
            for field_name, field_config in extract_config.items():
                # Handle nested_list type
                if field_config.get("type") == "nested_list":
                    value = self._extract_nested_list(response, field_config)
                elif field_config.get("type") == "ajax_nested_list":
                    value = await self._extract_ajax_nested_list(
                        response, field_config
                    )
                    # json_object returns a dict — merge flat into item
                    if isinstance(value, dict):
                        item.update(value)
                        continue
                else:
                    value = self._extract_field(response, field_config)

                # Apply processors if defined
                processors = field_config.get("processors", [])
                if processors:
                    value = apply_processors(value, processors)

                # Store custom fields directly on item (pipeline will move to metadata_json)
                item[field_name] = value

            logger.info(
                f"Extracted {len(extract_config)} fields from {response.url} using {callback_name}"
            )

            yield item

            # Increment counter
            self._items_scraped += 1

        return standard_callback
