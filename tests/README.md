# ScrapAI Test Suite

Complete testing infrastructure for ScrapAI CLI using pytest + hypothesis.

## Quick Start

```bash
# Install test dependencies
.venv/bin/pip install -r requirements-dev.txt

# Run all tests
make test

# Run only unit tests (fast)
make test-unit

# Run with coverage
make test-coverage

# Run specific test file
.venv/bin/pytest tests/unit/test_extractors_simple.py -v

# Run tests matching pattern
.venv/bin/pytest -k "extractor" -v
```

## Test Structure

```
tests/
├── conftest.py              # Shared fixtures (database, HTML samples, mocks)
├── unit/                    # Fast unit tests (no external dependencies)
│   └── test_extractors_simple.py
├── integration/             # Integration tests (database, spider execution)
│   └── test_database_spider.py
└── fixtures/                # Sample HTML files and test data
    └── README.md
```

## Test Markers

Organize and filter tests using pytest markers:

```bash
# Run only unit tests
pytest -m unit

# Run only integration tests
pytest -m integration

# Skip slow tests
pytest -m "not slow"

# Run only browser tests
pytest -m browser

# Run only Cloudflare tests
pytest -m cloudflare
```

Available markers:
- `unit` - Fast unit tests
- `integration` - Integration tests (database, spider execution)
- `slow` - Slow-running tests (property-based, full crawls)
- `browser` - Tests requiring Playwright/nodriver
- `cloudflare` - Tests requiring Cloudflare bypass
- `network` - Tests making real HTTP requests

## Writing Tests

### Unit Tests

Test individual components in isolation:

```python
import pytest
from core.extractors import NewspaperExtractor

class TestMyExtractor:
    @pytest.mark.unit
    def test_extracts_title(self, sample_html_simple):
        extractor = NewspaperExtractor()
        result = extractor.extract(
            url="https://example.com/article",
            html=sample_html_simple
        )
        assert result is not None
        assert len(result.title) > 0
```

### Integration Tests

Test complete workflows:

```python
import pytest
from spiders.database_spider import DatabaseSpider

class TestMySpider:
    @pytest.mark.integration
    def test_spider_loads_config(self, temp_db, sample_project_name):
        # Create spider in test database
        spider_config = Spider(name="test", project=sample_project_name)
        temp_db.add(spider_config)
        temp_db.commit()

        # Test spider initialization
        spider = DatabaseSpider(name="test", project_name=sample_project_name)
        assert spider.name == "test"
```

### Property-Based Tests

Test with random inputs using Hypothesis:

```python
from hypothesis import given, strategies as st

class TestRobustness:
    @pytest.mark.unit
    @pytest.mark.slow
    @given(html=st.text(min_size=10, max_size=1000))
    def test_never_crashes(self, html):
        extractor = NewspaperExtractor()
        result = extractor.extract("https://example.com", html)
        assert result is None or isinstance(result, ScrapedArticle)
```

## Fixtures

Common fixtures available in all tests (from `conftest.py`):

- `temp_db` - Temporary SQLite database with all tables
- `sample_project_name` - Sample project name
- `sample_spider_config` - Valid spider configuration dict
- `sample_html_simple` - Clean HTML with semantic tags
- `sample_html_complex` - Complex HTML requiring custom selectors
- `sample_html_malformed` - Malformed HTML for robustness testing
- `mock_scrapy_response` - Mock Scrapy Response objects
- `mock_browser_client` - Mock browser automation client
- `temp_data_dir` - Temporary data directory
- `test_data_dir` - Path to fixtures directory

## Code Coverage

View coverage report:

```bash
# Generate HTML coverage report
make test-coverage

# Open report in browser
open htmlcov/index.html
```

Target coverage:
- **Core modules**: 80%+
- **Spiders**: 70%+
- **CLI commands**: 60%+ (harder to test)

## Code Quality

Run linting and formatting:

```bash
# Format code with black
make format

# Check formatting
make format-check

# Lint with flake8
make lint

# Type check with mypy
make typecheck

# Run all quality checks
make pre-commit
```

## Security Scanning

Scan for vulnerabilities:

```bash
# Check dependencies for known vulnerabilities
make security-deps

# Scan code for security issues
make security-code

# Run all security checks
make security
```

## CI/CD

Tests run automatically on push/PR via GitHub Actions:

- Tests on Python 3.10, 3.11, 3.12, 3.13
- Code coverage uploaded to Codecov
- Security scans (safety + bandit)
- Code quality checks (black + flake8 + mypy)

See `.github/workflows/tests.yml`

## Tips

1. **Write tests first** - TDD helps design better APIs
2. **Use markers** - Organize tests by type (unit, integration, slow)
3. **Mock external dependencies** - Tests should be fast and reliable
4. **Test edge cases** - Empty HTML, malformed input, missing fields
5. **Use Hypothesis** - Catch bugs you didn't think of
6. **Keep tests focused** - One assertion per test when possible
7. **Use descriptive names** - `test_spider_handles_missing_config` not `test1`

## Next Steps

Tests to add:
- [ ] Cloudflare handler tests (mock browser interactions)
- [ ] CLI command tests (spider import/export, queue operations)
- [ ] Middleware tests
- [ ] Pipeline tests
- [ ] Settings validation tests
- [ ] URL extraction tests
- [ ] Browser automation tests

See `AUDIT.md` for full testing recommendations.
