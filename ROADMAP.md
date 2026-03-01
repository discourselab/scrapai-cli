# ScrapAI Roadmap

## Vision

**AI agents write spider configs. Humans share them. Stop rebuilding scrapers everyone needs.**

ScrapAI is infrastructure for reliable, reusable web scraping. Like npm for JavaScript or PyPI for Python, but for web scrapers.

## Current State (v0.x)

**What works today:**
- ✅ Database-first spider management (write once, use forever)
- ✅ CloakBrowser integration (Cloudflare bypass, JS rendering)
- ✅ Incremental crawling (DeltaFetch - only scrape new content)
- ✅ Smart proxy middleware (auto-escalation when blocked)
- ✅ Checkpoint pause/resume (production crawls)
- ✅ S3 uploads (automatic cloud backup)
- ✅ Multiple extraction strategies (newspaper, trafilatura, custom)
- ✅ Named callbacks (custom field extraction)
- ✅ Queue system (batch processing)
- ✅ Cross-platform (Linux, macOS, Windows via WSL)

**Test coverage:** 26% (critical modules: 70-100%)

## Phase 1: Spider Library (Q2 2026)

**Goal:** Make spiders shareable and reusable - the core value proposition.

### Spider Marketplace
**Problem:** Every developer/AI agent rebuilds scrapers for the same sites (NYT, BBC, Amazon, etc.)

**Solution:** Community library of production-ready spider configs

**Features:**
- **Spider registry** - Browse, search, download configs
- **Template gallery** - News, e-commerce, jobs, forums, government
- **Quality indicators** - Downloads, success rate, last updated, community ratings
- **Easy import** - `./scrapai spiders import --from-registry nytimes`
- **Versioning** - Track changes, rollback when sites update

**For developers:**
- Save days of development time
- Production-tested configs
- Community maintenance

**For AI agents (Claude Code, OpenClaw, etc.):**
- Skip Phase 1-4 spider building
- Instant data access - load config, start scraping
- No wasted compute on selector discovery

**Initial collection:** 50+ spiders for top news sites, e-commerce, job boards

### Spider Sharing & Publishing
- `./scrapai spiders publish <spider> --registry community`
- Markdown documentation template
- Example URLs and expected output
- License selection (MIT, Apache, CC0)

**Why first:** Network effect - more spiders = more users = more contributors

## Phase 2: Production Infrastructure (Q3 2026)

**Goal:** Make it reliable and programmable.

### Data Quality & Validation
**Problem:** Scraped data might be incomplete or wrong

**Features:**
- Schema validation (require fields: title, content, date)
- Quality scoring (completeness, content length)
- Anomaly detection (site changed, selectors broke)
- Auto-alerts (email, Slack, webhook) when spiders fail
- Validation reports per crawl

**Why:** Catch breakage early, maintain data integrity

### REST API for Programmatic Access
**Problem:** CLI-only limits integration

**Features:**
- RESTful API: run spiders, get results, manage configs
- Webhook notifications (crawl complete, spider failed)
- API keys and rate limiting
- OpenAPI/Swagger docs
- Python/JS client libraries

**Why:** Infrastructure for AI agents, integrations, automation

## Contributing

**Want to help shape the roadmap?**

- **Discussions:** [GitHub Discussions](https://github.com/discourselab/scrapai-cli/discussions)
- **Feature requests:** [GitHub Issues](https://github.com/discourselab/scrapai-cli/issues)
- **Spider contributions:** Coming in Phase 1 (Spider Marketplace)

**Priority is driven by:**
1. Community feedback (what you actually need)
2. Production pain points (what breaks in real usage)
3. Ecosystem trends (AI agents, new anti-bot systems)

## Versioning

- **Current:** v0.x (pre-1.0 alpha/beta)
- **v1.0 target:** Phase 1 complete (Spider Library + solid core)
- **v2.0 target:** Phase 2 complete (Data Quality + REST API)

Breaking changes expected until v1.0. We'll provide migration guides.

---

**Last updated:** March 2026
**Maintained by:** [DiscourseLab](https://www.discourselab.ai/)
