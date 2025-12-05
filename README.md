# ScrapAI-CLI

_Rethinking web scraping for the AI era_

## The Problem with AI-First Scraping

Most AI scraping solutions today use LLMs to parse every single webpage. This approach is fundamentally flawed:

- **Expensive**: $0.01-0.10 per page adds up fast across thousands of articles
- **Slow**: API latency makes large-scale extraction impractical
- **Inconsistent**: LLM outputs vary, making data quality unpredictable
- **Wasteful**: If you can parse one URL, why use AI for 1000 identical pages?

## Our Philosophy: Code Once, Run Deterministically

**ScrapAI-CLI inverts this paradigm.**

Instead of using AI to parse content, we use AI to **write parsing code**. Once written, that code runs deterministically at scale with zero ongoing AI costs.

```
Traditional AI Scraping:
Website → LLM → Structured Data (for every page)
Cost: $0.05 × 10,000 pages = $500

ScrapAI Approach:
Website → AI Agent → Code → Structured Data (for all pages)
Cost: $0.50 (one-time) × 10,000 pages = $0.50
```

## How It Works

1. **AI Agent Analyzes**: Claude Code inspects a website and understands its structure
2. **Generates Configuration**: Creates JSON rules for content extraction (no Python files)
3. **Stores in Database**: Rules become persistent, versioned configurations
4. **Scales Infinitely**: Scrapy engine processes thousands of pages using those rules

The AI cost is amortized across all future extractions from that domain.

## Benefits

- **99% Cost Reduction**: Pay for intelligence once, not per page
- **Lightning Fast**: No API calls during extraction
- **100% Reproducible**: Deterministic code-based parsing
- **Production Ready**: Built on battle-tested Scrapy + PostgreSQL
- **Human Auditable**: JSON configurations are readable and debuggable

## When to Use This

✅ **Perfect for:**

- News sites with consistent article structure
- E-commerce catalogs with product pages
- Any site where you need >100 pages from the same domain
- Production workloads requiring speed and cost predictability

❌ **Not ideal for:**

- One-off page extractions (just use ChatGPT)
- Highly dynamic sites with constantly changing structure
- Sites requiring complex reasoning about content

---

_"Why think when you can remember?"_

For setup instructions and technical details, see `CLAUDE.md`.
