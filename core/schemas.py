from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
import ipaddress
import re
import socket
from urllib.parse import urlparse


class ScrapedArticle(BaseModel):
    """Standardized model for scraped article data.

    Title/content can be empty — the framework no longer rejects content-light
    pages (video-only, image-only, very short notices). Validation against the
    project schema's `required` contract happens in Phase 4 of the agent
    workflow, not here. See CLAUDE.md "Schema-driven extraction".
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    url: str
    title: str = ""
    content: str = ""
    author: Optional[str] = None
    published_date: Optional[datetime] = None
    source: str
    extracted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Optional[Dict[str, Any]] = {}
    html: Optional[str] = None
    clean_html: Optional[str] = None
    markdown: Optional[str] = None
    top_image: Optional[str] = None
    images: List[Dict[str, str]] = []
    videos: List[Dict[str, str]] = []


class SpiderRuleSchema(BaseModel):
    """Schema for spider URL matching rules."""

    model_config = ConfigDict(extra="forbid")

    allow: Optional[List[str]] = Field(
        default=None, description="URL patterns to allow (regex)"
    )
    deny: Optional[List[str]] = Field(
        default=None, description="URL patterns to deny (regex)"
    )
    restrict_xpaths: Optional[List[str]] = Field(
        default=None, description="XPath restrictions"
    )
    restrict_css: Optional[List[str]] = Field(
        default=None, description="CSS selector restrictions"
    )
    tags: Optional[List[str]] = Field(
        default=None,
        description=(
            "HTML tags LinkExtractor scans (default: ['a', 'area']). "
            "Include 'link' for <link rel=next> pagination."
        ),
    )
    callback: Optional[str] = Field(default=None, description="Callback function name")
    follow: bool = Field(
        default=True, description="Whether to follow links matching this rule"
    )
    priority: int = Field(
        default=0, ge=0, le=1000, description="Rule priority (0-1000)"
    )

    @field_validator("allow", "deny", "restrict_xpaths", "restrict_css", "tags")
    @classmethod
    def validate_patterns(cls, v):
        """Validate that patterns are non-empty strings if provided."""
        if v is not None:
            if not isinstance(v, list):
                raise ValueError("Must be a list of strings")
            for pattern in v:
                if not isinstance(pattern, str) or len(pattern.strip()) == 0:
                    raise ValueError("Patterns must be non-empty strings")
        return v

    @field_validator("callback")
    @classmethod
    def validate_callback(cls, v):
        """Validate callback is a valid Python identifier."""
        if v is not None:
            if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", v):
                raise ValueError(
                    f"Invalid callback name: {v}. Must be a valid Python identifier."
                )
        return v


class PaginatedListingSchema(BaseModel):
    """Config for a JS-paginated listing page.

    The spider opens `url` in a browser, collects hrefs matching
    `link_selector`, clicks `next_selector`, and repeats until the Next
    button disappears, `max_pages` is reached, or a page yields no new URLs.
    Each collected URL is crawled via parse_article.
    """

    model_config = ConfigDict(extra="forbid")

    url: str = Field(..., description="Listing URL to paginate")
    link_selector: str = Field(
        ..., description="CSS selector for article links on each page"
    )
    next_selector: str = Field(..., description="CSS selector for the Next button")
    wait_selector: Optional[str] = Field(
        default=None,
        description="CSS selector to wait for after each click (signals new content)",
    )
    max_pages: int = Field(
        default=100, ge=1, le=1000, description="Safety cap on page clicks"
    )
    click_delay: float = Field(
        default=1.5, ge=0.5, le=10, description="Seconds to wait after each Next click"
    )


class ProcessorSchema(BaseModel):
    """Schema for field processors."""

    model_config = ConfigDict(extra="allow")  # Allow processor-specific params

    type: str = Field(..., description="Processor type")

    @field_validator("type")
    @classmethod
    def validate_processor_type(cls, v):
        """Validate processor type is one of the allowed processors."""
        allowed = {
            "strip",
            "replace",
            "regex",
            "cast",
            "join",
            "default",
            "lowercase",
            "parse_datetime",
        }
        if v not in allowed:
            raise ValueError(
                f"Unknown processor type: {v}. Allowed: {', '.join(sorted(allowed))}"
            )
        return v


class FieldExtractDirective(BaseModel):
    """Per-spider directive for populating a project schema field.

    One of `from_field`, `css`, or `xpath` is required.
    - `from_field` pulls a value already produced by the article extractor
      (e.g. "markdown", "top_image", "images", "videos").
    - `css` / `xpath` runs a selector against the response, like a callback's
      extract config. Supports `get_all` for lists and `processors` for cleanup.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_field: Optional[str] = Field(
        default=None,
        alias="from",
        description="Name of an extractor-computed field to pull from",
    )
    css: Optional[str] = Field(default=None, description="CSS selector")
    xpath: Optional[str] = Field(default=None, description="XPath selector")
    get_all: bool = Field(
        default=False, description="Return all matches as a list (default: first only)"
    )
    to_text: bool = Field(
        default=False,
        description=(
            "Extract joined whitespace-stripped descendant text of the matched "
            "element (equivalent to bs4 `get_text(separator=' ', strip=True)`)"
        ),
    )
    to_markdown: bool = Field(
        default=False,
        description=(
            "Extract outer HTML of the matched element and convert to markdown "
            "via markdownify (ATX heading style)"
        ),
    )
    processors: Optional[List[ProcessorSchema]] = Field(
        default=None, description="Processors to apply to extracted value"
    )

    @model_validator(mode="after")
    def validate_has_source(self):
        if not self.from_field and not self.css and not self.xpath:
            raise ValueError(
                "field_extract directive requires one of 'from', 'css', or 'xpath'"
            )
        if (self.to_text or self.to_markdown) and self.get_all:
            raise ValueError(
                "to_text/to_markdown are not compatible with get_all (single element only)"
            )
        if self.to_text and self.to_markdown:
            raise ValueError("Pick one of to_text or to_markdown, not both")
        return self


class SpiderSettingsSchema(BaseModel):
    """Schema for spider settings (flexible key-value pairs)."""

    model_config = ConfigDict(extra="allow")  # Allow any settings

    # Common settings with validation
    EXTRACTOR_ORDER: Optional[List[str]] = Field(default=None)
    CUSTOM_SELECTORS: Optional[Dict[str, str]] = Field(default=None)
    CONCURRENT_REQUESTS: Optional[int] = Field(default=None, ge=1, le=32)
    DOWNLOAD_DELAY: Optional[float] = Field(default=None, ge=0, le=60)
    CLOUDFLARE_ENABLED: Optional[bool] = Field(default=None)
    CLOUDFLARE_STRATEGY: Optional[str] = Field(default=None)
    DELTAFETCH_ENABLED: Optional[bool] = Field(default=None)
    PLAYWRIGHT_WAIT_SELECTOR: Optional[str] = Field(default=None)
    INFINITE_SCROLL: Optional[bool] = Field(default=None)
    PAGINATED_LISTINGS: Optional[List[PaginatedListingSchema]] = Field(
        default=None,
        description="JS-paginated listings to enumerate via browser clicks at crawl start",
    )
    FIELDS: Optional[Dict[str, FieldExtractDirective]] = Field(
        default=None,
        description=(
            "Per-spider directives for populating project schema fields. Keyed by "
            "schema field name. Each directive uses `from`, `css`, or `xpath`."
        ),
    )
    FIELD_EXTRACT: Optional[Dict[str, FieldExtractDirective]] = Field(
        default=None,
        description="Back-compat alias for FIELDS (FIELDS wins if both set).",
    )

    @field_validator("EXTRACTOR_ORDER")
    @classmethod
    def validate_extractor_order(cls, v):
        """Validate extractor order contains known extractors."""
        if v is not None:
            allowed = {"newspaper", "trafilatura", "custom", "playwright"}
            for extractor in v:
                if extractor not in allowed:
                    raise ValueError(
                        f"Unknown extractor: {extractor}. Allowed: {allowed}"
                    )
        return v

    @field_validator("CLOUDFLARE_STRATEGY")
    @classmethod
    def validate_cloudflare_strategy(cls, v):
        """Validate Cloudflare strategy is valid."""
        if v is not None:
            allowed = {"hybrid", "browser_only"}
            if v.lower() not in allowed:
                raise ValueError(
                    f"Invalid Cloudflare strategy: {v}. Allowed: {allowed}"
                )
        return v


class FieldExtractSchema(BaseModel):
    """Schema for field extraction configuration."""

    model_config = ConfigDict(extra="forbid")

    css: Optional[str] = Field(default=None, description="CSS selector")
    xpath: Optional[str] = Field(default=None, description="XPath selector")
    get_all: Optional[bool] = Field(
        default=False, description="Extract all matches (returns list)"
    )
    processors: Optional[List[ProcessorSchema]] = Field(
        default=None, description="Processors to apply to extracted value"
    )
    to_text: Optional[bool] = Field(
        default=False,
        description=(
            "Extract joined whitespace-stripped descendant text of the matched "
            "element (bs4 get_text(separator=' ', strip=True) equivalent)"
        ),
    )
    to_markdown: Optional[bool] = Field(
        default=False,
        description=(
            "Convert outer HTML of the matched element to markdown via "
            "markdownify (ATX heading style)"
        ),
    )

    # For nested list extraction
    type: Optional[str] = Field(
        default=None, description="Field type (e.g., 'nested_list', 'ajax_nested_list')"
    )
    selector: Optional[str] = Field(
        default=None, description="CSS selector for nested list items"
    )
    extract: Optional[Dict[str, Any]] = Field(
        default=None, description="Nested extraction config"
    )

    # For ajax_nested_list extraction
    ajax_url: Optional[str] = Field(
        default=None, description="AJAX endpoint URL (relative or absolute)"
    )
    ajax_data: Optional[Dict[str, str]] = Field(
        default=None, description="POST data for AJAX request"
    )
    post_id_css: Optional[str] = Field(
        default=None, description="CSS selector to extract post ID from page"
    )
    response_json_field: Optional[str] = Field(
        default=None,
        description="Dot-path to HTML in JSON response (e.g., 'data.comment_list')",
    )
    post_id_regex: Optional[str] = Field(
        default=None,
        description="Regex to extract post ID from post_id_css value (must have 1 capture group)",
    )
    ajax_method: Optional[str] = Field(
        default=None,
        description="HTTP method for AJAX request: GET or POST (default: POST)",
    )
    response_type: Optional[str] = Field(
        default=None,
        description=(
            "Response type: json_html (HTML inside JSON), "
            "json_array (JSON array), or json_object (single JSON object)"
        ),
    )
    ajax_per_page: Optional[int] = Field(
        default=None,
        description="Items per page for AJAX pagination (0 = no pagination)",
    )
    json_path: Optional[str] = Field(
        default=None,
        description="Dot-path to extract value from JSON object (for json_array response_type)",
    )
    nest_replies: Optional[bool] = Field(
        default=None,
        description="Nest reply items under parent items using comment_id/parent_id fields",
    )
    comment_id_field: Optional[str] = Field(
        default=None, description="Field name for comment ID (default: comment_id)"
    )
    parent_id_field: Optional[str] = Field(
        default=None,
        description="Field name for parent comment ID (default: parent_id)",
    )
    replies_field: Optional[str] = Field(
        default=None,
        description="Field name for nested replies array (default: replies)",
    )

    @model_validator(mode="after")
    def validate_selector_or_nested(self):
        """Validate that either a selector (css/xpath) or nested config is provided."""
        has_selector = self.css or self.xpath
        is_nested = self.type == "nested_list"
        is_ajax = self.type == "ajax_nested_list"

        if not has_selector and not is_nested and not is_ajax:
            raise ValueError(
                "Field must have either 'css' or 'xpath' selector, "
                "or be a nested_list/ajax_nested_list with 'selector' and 'extract' fields"
            )

        if is_nested and (not self.selector or not self.extract):
            raise ValueError(
                "nested_list fields must have both 'selector' and 'extract' fields"
            )

        if is_ajax and (not self.ajax_url or not self.selector or not self.extract):
            raise ValueError(
                "ajax_nested_list fields must have 'ajax_url', 'selector', and 'extract' fields"
            )

        if (self.to_text or self.to_markdown) and self.get_all:
            raise ValueError(
                "to_text/to_markdown are not compatible with get_all (single element only)"
            )
        if self.to_text and self.to_markdown:
            raise ValueError("Pick one of to_text or to_markdown, not both")

        return self


class UrlContextFieldSchema(BaseModel):
    """Schema for extracting fields from the page URL via regex."""

    model_config = ConfigDict(extra="forbid")

    regex: str = Field(..., description="Regex pattern with one capture group")

    @field_validator("regex")
    @classmethod
    def validate_regex(cls, v):
        """Validate regex compiles and has exactly one capture group."""
        try:
            compiled = re.compile(v)
        except re.error as e:
            raise ValueError(f"Invalid regex pattern: {e}")
        if compiled.groups != 1:
            raise ValueError(
                f"Regex must have exactly one capture group, found {compiled.groups}"
            )
        return v


class IterateFollowSchema(BaseModel):
    """Schema for iterate follow configuration (URL selector + target callback)."""

    model_config = ConfigDict(extra="forbid")

    url: FieldExtractSchema = Field(
        ..., description="Selector for the follow URL (css/xpath)"
    )
    callback: str = Field(..., description="Target callback name for followed URLs")

    @field_validator("callback")
    @classmethod
    def validate_callback_name(cls, v):
        """Validate callback is a valid Python identifier."""
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", v):
            raise ValueError(
                f"Invalid callback name: {v}. Must be a valid Python identifier."
            )
        return v


class IterateSchema(BaseModel):
    """Schema for iterate configuration (loop over listing rows)."""

    model_config = ConfigDict(extra="forbid")

    selector: str = Field(
        ..., min_length=1, description="CSS selector for row elements"
    )
    follow: IterateFollowSchema = Field(
        ..., description="Follow configuration (URL + callback)"
    )
    url_context: Optional[Dict[str, UrlContextFieldSchema]] = Field(
        default=None, description="Fields to extract from the page URL via regex"
    )


class CallbackSchema(BaseModel):
    """Schema for callback extraction configuration."""

    model_config = ConfigDict(extra="forbid")

    extract: Optional[Dict[str, FieldExtractSchema]] = Field(
        default=None, description="Field extraction rules"
    )
    iterate: Optional[IterateSchema] = Field(
        default=None, description="Iterate over listing rows and follow detail pages"
    )

    @model_validator(mode="after")
    def validate_has_extract_or_iterate(self):
        """Require at least one of extract or iterate."""
        has_extract = self.extract and len(self.extract) > 0
        has_iterate = self.iterate is not None
        if not has_extract and not has_iterate:
            raise ValueError(
                "Callback must have at least one of 'extract' (non-empty) or 'iterate'"
            )
        return self


class SpiderConfigSchema(BaseModel):
    """Schema for complete spider configuration (JSON import)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=255, description="Spider name")
    source_url: str = Field(..., min_length=1, description="Original website URL")
    allowed_domains: List[str] = Field(..., min_items=1, description="Allowed domains")
    start_urls: List[str] = Field(..., min_items=1, description="Starting URLs")
    rules: List[SpiderRuleSchema] = Field(
        default_factory=list, description="URL matching rules"
    )
    settings: SpiderSettingsSchema = Field(
        default_factory=SpiderSettingsSchema, description="Spider settings"
    )
    callbacks: Optional[Dict[str, CallbackSchema]] = Field(
        default=None, description="Named callback extraction configurations"
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        """Validate spider name is safe (alphanumeric, underscore, hyphen only)."""
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError(
                f"Invalid spider name: {v}. "
                "Only alphanumeric characters, underscores, and hyphens allowed."
            )
        # The alphanumeric check above already prevents SQL injection
        # (no spaces, quotes, semicolons, etc. allowed)
        # No need for additional keyword checking
        return v

    @field_validator("source_url", "start_urls")
    @classmethod
    def validate_urls(cls, v):
        """Validate URLs are well-formed and use safe schemes."""
        if isinstance(v, str):
            urls = [v]
        else:
            urls = v

        allowed_schemes = {"http", "https"}

        for url in urls:
            # Basic URL validation
            if not url or len(url.strip()) == 0:
                raise ValueError("URL cannot be empty")

            # Check scheme
            url_lower = url.lower()
            if not any(
                url_lower.startswith(f"{scheme}://") for scheme in allowed_schemes
            ):
                raise ValueError(
                    f"Invalid URL scheme: {url}. Only HTTP and HTTPS are allowed. "
                    "This prevents file://, ftp://, and other potentially dangerous schemes."
                )

            # Prevent SSRF to localhost/private IPs
            # Parse hostname and resolve to catch all encodings
            # (hex IPs, octal, IPv6 mapped, etc.)
            parsed = urlparse(url)
            hostname = parsed.hostname  # lowercased, brackets stripped
            if hostname:
                # Check string patterns first (catches "localhost" etc.)
                if hostname in ("localhost", "0.0.0.0"):
                    raise ValueError(
                        f"URL points to localhost: {url}. "
                        "Blocked to prevent SSRF attacks."
                    )
                # Try parsing as IP directly (handles hex, octal, decimal)
                try:
                    ip = ipaddress.ip_address(hostname)
                    if (
                        ip.is_private
                        or ip.is_loopback
                        or ip.is_link_local
                        or ip.is_reserved
                    ):
                        raise ValueError(
                            f"URL points to private/reserved IP: {url}. "
                            "Blocked to prevent SSRF attacks."
                        )
                except ValueError as ip_err:
                    if "Blocked to prevent SSRF" in str(ip_err):
                        raise
                    # Not an IP literal — resolve the hostname
                    try:
                        results = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC)
                        for family, _, _, _, sockaddr in results:
                            ip = ipaddress.ip_address(sockaddr[0])
                            if (
                                ip.is_private
                                or ip.is_loopback
                                or ip.is_link_local
                                or ip.is_reserved
                            ):
                                raise ValueError(
                                    f"URL hostname '{hostname}' resolves to "
                                    f"private IP {ip}: {url}. "
                                    "Blocked to prevent SSRF attacks."
                                )
                    except socket.gaierror:
                        pass  # unresolvable host — let Scrapy handle it

            # Basic length check
            if len(url) > 2048:
                raise ValueError(f"URL too long (max 2048 chars): {url[:50]}...")

        return v

    @field_validator("callbacks")
    @classmethod
    def validate_callbacks(cls, v):
        """Validate callback names are valid identifiers and not reserved."""
        if v is None:
            return v

        reserved_names = {
            "parse_article",
            "parse_start_url",
            "start_requests",
            "from_crawler",
            "closed",
            "parse",
        }

        for callback_name in v.keys():
            # Must be valid Python identifier
            if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", callback_name):
                raise ValueError(
                    f"Invalid callback name: '{callback_name}'. "
                    "Must be a valid Python identifier."
                )

            # Must not be reserved
            if callback_name in reserved_names:
                raise ValueError(
                    f"Callback name '{callback_name}' is reserved and cannot be used. "
                    f"Reserved names: {', '.join(sorted(reserved_names))}"
                )

        return v

    @model_validator(mode="after")
    def validate_rule_callbacks(self):
        """Cross-validate that rules reference defined callbacks."""
        if not self.callbacks or not self.rules:
            return self

        defined_callbacks = set(self.callbacks.keys())
        # Add built-in callbacks that are always available
        defined_callbacks.update({"parse_article", None})

        for idx, rule in enumerate(self.rules):
            if rule.callback and rule.callback not in defined_callbacks:
                raise ValueError(
                    f"Rule {idx} references undefined callback: '{rule.callback}'. "
                    f"Defined callbacks: {', '.join(sorted(c for c in defined_callbacks if c))}"
                )

        return self

    @model_validator(mode="after")
    def validate_iterate_follow_callbacks(self):
        """Cross-validate that iterate.follow.callback references a defined callback."""
        if not self.callbacks:
            return self

        defined_callbacks = set(self.callbacks.keys())
        defined_callbacks.add("parse_article")

        for cb_name, cb_config in self.callbacks.items():
            if cb_config.iterate and cb_config.iterate.follow:
                target = cb_config.iterate.follow.callback
                if target not in defined_callbacks:
                    raise ValueError(
                        f"Callback '{cb_name}' iterate.follow.callback references "
                        f"undefined callback: '{target}'. "
                        f"Defined callbacks: {', '.join(sorted(defined_callbacks))}"
                    )

        return self

    @field_validator("allowed_domains")
    @classmethod
    def validate_domains(cls, v):
        """Validate domains are reasonable."""
        for domain in v:
            if not domain or len(domain.strip()) == 0:
                raise ValueError("Domain cannot be empty")

            # Prevent localhost/private domains
            domain_lower = domain.lower()
            dangerous = ["localhost", "127.0.0.1", "0.0.0.0", "::1"]
            if any(host in domain_lower for host in dangerous):
                raise ValueError(
                    f"Domain points to localhost: {domain}. Blocked to prevent SSRF."
                )

            # Basic domain format check
            if not re.match(
                r"^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$",
                domain,
            ):
                raise ValueError(f"Invalid domain format: {domain}")

        return v
