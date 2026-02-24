"""
Unit tests for input validation (Pydantic schemas).

Tests that spider configuration imports are properly validated.
"""

import pytest
from pydantic import ValidationError

from core.schemas import SpiderConfigSchema, SpiderRuleSchema, SpiderSettingsSchema


class TestSpiderNameValidation:
    """Test spider name validation."""

    @pytest.mark.unit
    def test_valid_spider_name(self):
        """Test that valid spider names are accepted."""
        config = {
            "name": "valid_spider_name",
            "source_url": "https://example.com",
            "allowed_domains": ["example.com"],
            "start_urls": ["https://example.com/"],
        }
        spider = SpiderConfigSchema(**config)
        assert spider.name == "valid_spider_name"

    @pytest.mark.unit
    def test_spider_name_with_hyphens(self):
        """Test that spider names with hyphens are accepted."""
        config = {
            "name": "spider-with-hyphens",
            "source_url": "https://example.com",
            "allowed_domains": ["example.com"],
            "start_urls": ["https://example.com/"],
        }
        spider = SpiderConfigSchema(**config)
        assert spider.name == "spider-with-hyphens"

    @pytest.mark.unit
    def test_invalid_spider_name_with_spaces(self):
        """Test that spider names with spaces are rejected."""
        config = {
            "name": "spider with spaces",
            "source_url": "https://example.com",
            "allowed_domains": ["example.com"],
            "start_urls": ["https://example.com/"],
        }
        with pytest.raises(ValidationError) as exc_info:
            SpiderConfigSchema(**config)
        assert "Only alphanumeric" in str(exc_info.value)

    @pytest.mark.unit
    def test_invalid_spider_name_sql_injection(self):
        """Test that SQL injection attempts in names are blocked by alphanumeric validation."""
        dangerous_names = [
            "spider'; DROP TABLE spiders; --",
            "spider; DELETE FROM spiders",
            "spider/*comment*/",
        ]
        for name in dangerous_names:
            config = {
                "name": name,
                "source_url": "https://example.com",
                "allowed_domains": ["example.com"],
                "start_urls": ["https://example.com/"],
            }
            with pytest.raises(ValidationError) as exc_info:
                SpiderConfigSchema(**config)
            # SQL injection is blocked by alphanumeric validation (no quotes, semicolons, etc.)
            error_msg = str(exc_info.value).lower()
            assert "invalid spider name" in error_msg or "alphanumeric" in error_msg

    @pytest.mark.unit
    def test_valid_spider_name_with_keywords(self):
        """Test that spider names containing SQL keywords as substrings are allowed."""
        # These should be VALID (keyword is part of normal word)
        valid_names = [
            "news_update_spider",  # contains "update"
            "article_selector",  # contains "select"
            "data_insertion_bot",  # contains "insert"
        ]
        for name in valid_names:
            config = {
                "name": name,
                "source_url": "https://example.com",
                "allowed_domains": ["example.com"],
                "start_urls": ["https://example.com/"],
            }
            spider = SpiderConfigSchema(**config)
            assert spider.name == name


class TestURLValidation:
    """Test URL validation (SSRF prevention)."""

    @pytest.mark.unit
    def test_valid_https_url(self):
        """Test that HTTPS URLs are accepted."""
        config = {
            "name": "test",
            "source_url": "https://example.com",
            "allowed_domains": ["example.com"],
            "start_urls": ["https://example.com/page"],
        }
        spider = SpiderConfigSchema(**config)
        assert spider.source_url == "https://example.com"

    @pytest.mark.unit
    def test_valid_http_url(self):
        """Test that HTTP URLs are accepted."""
        config = {
            "name": "test",
            "source_url": "http://example.com",
            "allowed_domains": ["example.com"],
            "start_urls": ["http://example.com/"],
        }
        spider = SpiderConfigSchema(**config)
        assert spider.source_url == "http://example.com"

    @pytest.mark.unit
    def test_invalid_file_scheme(self):
        """Test that file:// URLs are blocked (SSRF prevention)."""
        config = {
            "name": "test",
            "source_url": "file:///etc/passwd",
            "allowed_domains": ["example.com"],
            "start_urls": ["https://example.com/"],
        }
        with pytest.raises(ValidationError) as exc_info:
            SpiderConfigSchema(**config)
        assert "HTTP and HTTPS" in str(exc_info.value)

    @pytest.mark.unit
    def test_invalid_ftp_scheme(self):
        """Test that ftp:// URLs are blocked."""
        config = {
            "name": "test",
            "source_url": "ftp://example.com/file",
            "allowed_domains": ["example.com"],
            "start_urls": ["https://example.com/"],
        }
        with pytest.raises(ValidationError) as exc_info:
            SpiderConfigSchema(**config)
        assert "HTTP and HTTPS" in str(exc_info.value)

    @pytest.mark.unit
    def test_ssrf_localhost(self):
        """Test that localhost URLs are blocked (SSRF prevention)."""
        localhost_urls = [
            "http://localhost/admin",
            "http://127.0.0.1/secret",
            "http://0.0.0.0/",
            "http://[::1]/api",
        ]
        for url in localhost_urls:
            config = {
                "name": "test",
                "source_url": url,
                "allowed_domains": ["example.com"],
                "start_urls": ["https://example.com/"],
            }
            with pytest.raises(ValidationError) as exc_info:
                SpiderConfigSchema(**config)
            assert "localhost or private IP" in str(exc_info.value)

    @pytest.mark.unit
    def test_ssrf_private_ip(self):
        """Test that private IP addresses are blocked (SSRF prevention)."""
        private_ips = [
            "http://192.168.1.1/",
            "http://10.0.0.1/",
            "http://172.16.0.1/",
            "http://169.254.169.254/metadata",  # AWS metadata endpoint
        ]
        for url in private_ips:
            config = {
                "name": "test",
                "source_url": "https://example.com",
                "allowed_domains": ["example.com"],
                "start_urls": [url],
            }
            with pytest.raises(ValidationError) as exc_info:
                SpiderConfigSchema(**config)
            assert "localhost or private IP" in str(exc_info.value)


class TestDomainValidation:
    """Test domain validation."""

    @pytest.mark.unit
    def test_valid_domain(self):
        """Test that valid domains are accepted."""
        config = {
            "name": "test",
            "source_url": "https://example.com",
            "allowed_domains": ["example.com", "sub.example.com"],
            "start_urls": ["https://example.com/"],
        }
        spider = SpiderConfigSchema(**config)
        assert "example.com" in spider.allowed_domains

    @pytest.mark.unit
    def test_invalid_domain_localhost(self):
        """Test that localhost domains are blocked."""
        config = {
            "name": "test",
            "source_url": "https://example.com",
            "allowed_domains": ["localhost"],
            "start_urls": ["https://example.com/"],
        }
        with pytest.raises(ValidationError) as exc_info:
            SpiderConfigSchema(**config)
        assert "localhost" in str(exc_info.value).lower()

    @pytest.mark.unit
    def test_invalid_domain_format(self):
        """Test that invalid domain formats are rejected."""
        invalid_domains = [
            "not a domain",
            "domain..com",
            ".example.com",
            "example.com.",
        ]
        for domain in invalid_domains:
            config = {
                "name": "test",
                "source_url": "https://example.com",
                "allowed_domains": [domain],
                "start_urls": ["https://example.com/"],
            }
            with pytest.raises(ValidationError):
                SpiderConfigSchema(**config)


class TestRuleValidation:
    """Test spider rule validation."""

    @pytest.mark.unit
    def test_valid_rule(self):
        """Test that valid rules are accepted."""
        rule = SpiderRuleSchema(
            allow=[r"/article/.*"], deny=[r"/tag/.*"], follow=True, priority=100
        )
        assert rule.follow is True
        assert rule.priority == 100

    @pytest.mark.unit
    def test_invalid_callback_name(self):
        """Test that invalid callback names are rejected."""
        invalid_callbacks = [
            "callback with spaces",
            "callback-with-dashes",
            "123callback",  # Can't start with number
            "callback.method",
        ]
        for callback in invalid_callbacks:
            with pytest.raises(ValidationError) as exc_info:
                SpiderRuleSchema(callback=callback)
            assert "Invalid callback" in str(exc_info.value)

    @pytest.mark.unit
    def test_valid_callback_name(self):
        """Test that valid callback names are accepted."""
        valid_callbacks = ["parse_article", "parse", "callback_1", "_private_callback"]
        for callback in valid_callbacks:
            rule = SpiderRuleSchema(callback=callback)
            assert rule.callback == callback

    @pytest.mark.unit
    def test_priority_bounds(self):
        """Test that priority is bounded 0-1000."""
        # Valid priorities
        for priority in [0, 100, 500, 1000]:
            rule = SpiderRuleSchema(priority=priority)
            assert rule.priority == priority

        # Invalid priorities
        for priority in [-1, 1001, 9999]:
            with pytest.raises(ValidationError):
                SpiderRuleSchema(priority=priority)


class TestSettingsValidation:
    """Test spider settings validation."""

    @pytest.mark.unit
    def test_valid_extractor_order(self):
        """Test that valid extractor orders are accepted."""
        settings = SpiderSettingsSchema(
            EXTRACTOR_ORDER=["newspaper", "trafilatura", "custom"]
        )
        assert "newspaper" in settings.EXTRACTOR_ORDER

    @pytest.mark.unit
    def test_invalid_extractor(self):
        """Test that invalid extractors are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SpiderSettingsSchema(EXTRACTOR_ORDER=["newspaper", "invalid_extractor"])
        assert "Unknown extractor" in str(exc_info.value)

    @pytest.mark.unit
    def test_valid_cloudflare_strategy(self):
        """Test that valid Cloudflare strategies are accepted."""
        for strategy in ["hybrid", "browser_only", "HYBRID", "BROWSER_ONLY"]:
            SpiderSettingsSchema(CLOUDFLARE_STRATEGY=strategy)
            # Should not raise

    @pytest.mark.unit
    def test_invalid_cloudflare_strategy(self):
        """Test that invalid Cloudflare strategies are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SpiderSettingsSchema(CLOUDFLARE_STRATEGY="invalid_strategy")
        assert "Invalid Cloudflare strategy" in str(exc_info.value)

    @pytest.mark.unit
    def test_concurrent_requests_bounds(self):
        """Test that concurrent requests is bounded 1-32."""
        # Valid
        for value in [1, 8, 16, 32]:
            settings = SpiderSettingsSchema(CONCURRENT_REQUESTS=value)
            assert settings.CONCURRENT_REQUESTS == value

        # Invalid
        for value in [0, -1, 33, 100]:
            with pytest.raises(ValidationError):
                SpiderSettingsSchema(CONCURRENT_REQUESTS=value)


class TestCompleteSpiderValidation:
    """Test complete spider configuration validation."""

    @pytest.mark.unit
    def test_minimal_valid_spider(self):
        """Test minimal valid spider configuration."""
        config = {
            "name": "minimal_spider",
            "source_url": "https://example.com",
            "allowed_domains": ["example.com"],
            "start_urls": ["https://example.com/"],
        }
        spider = SpiderConfigSchema(**config)
        assert spider.name == "minimal_spider"
        assert len(spider.rules) == 0  # Empty rules list
        assert spider.settings is not None  # Default settings

    @pytest.mark.unit
    def test_complete_valid_spider(self):
        """Test complete valid spider configuration."""
        config = {
            "name": "complete_spider",
            "source_url": "https://example.com",
            "allowed_domains": ["example.com"],
            "start_urls": ["https://example.com/", "https://example.com/news"],
            "rules": [
                {
                    "allow": [r"/article/.*"],
                    "deny": [r"/tag/.*"],
                    "follow": True,
                    "priority": 100,
                }
            ],
            "settings": {
                "EXTRACTOR_ORDER": ["newspaper", "trafilatura"],
                "CONCURRENT_REQUESTS": 8,
                "DOWNLOAD_DELAY": 1.5,
            },
        }
        spider = SpiderConfigSchema(**config)
        assert len(spider.rules) == 1
        assert spider.settings.CONCURRENT_REQUESTS == 8

    @pytest.mark.unit
    def test_extra_fields_rejected(self):
        """Test that extra unexpected fields are rejected."""
        config = {
            "name": "test",
            "source_url": "https://example.com",
            "allowed_domains": ["example.com"],
            "start_urls": ["https://example.com/"],
            "unexpected_field": "value",
        }
        with pytest.raises(ValidationError) as exc_info:
            SpiderConfigSchema(**config)
        assert "unexpected_field" in str(exc_info.value).lower()
