# Test Fixtures

This directory contains sample HTML files and test data for testing ScrapAI extractors.

## Directory Structure

```
fixtures/
├── html/           # Sample HTML files from real websites
│   ├── bbc.html
│   ├── cnn.html
│   ├── techcrunch.html
│   └── blog.html
├── configs/        # Sample spider configurations
│   └── sample_spider.json
└── README.md
```

## Adding New Fixtures

When adding new HTML fixtures:

1. Save real article HTML: `curl https://example.com/article > fixtures/html/example.html`
2. Remove scripts, tracking pixels, ads (keep only article content)
3. Document expected extraction results in comments
4. Create corresponding test in `test_extractors.py`

## Usage in Tests

```python
from pathlib import Path

def test_extractor(test_data_dir):
    html_file = test_data_dir / "html" / "bbc.html"
    html = html_file.read_text()

    result = extractor.extract(url="...", html=html)
    assert result.title == "Expected Title"
```
