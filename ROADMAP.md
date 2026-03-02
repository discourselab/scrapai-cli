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

## Phase 1A: Minimal REST API + Health Checks (Q2 2026 - Month 1-2)

**Goal:** Enable programmatic access, single-article scraping, and automated maintenance.

### Spider Health Checks ✅ (Shipped)

**Command:** `./scrapai health --project <name>`

Tests all spiders in a project, detects extraction vs crawling failures, generates markdown reports for agent-assisted fixes.

**Benefits:**
- Catch breakage early (monthly cron jobs)
- Agent fixes in 10 min vs 45 min manual
- Scales to 100+ spiders (270 hrs/year saved)
- See [docs/health.md](docs/health.md)

### Core API Endpoints

**Single Article Scraping** (the killer feature):
```bash
POST /api/scrape
{
  "url": "https://nytimes.com/2026/03/02/article",
  "spider": "nytimes"  # Uses saved CSS selectors from DB
}
# Returns: title, content, author, date in ~2 seconds
```

**Use cases:**
- Extract single article without full crawl
- RSS feed integration (scrape on publish)
- Real-time monitoring
- AI agents testing spider configs
- Manual URL paste → instant extraction

**Other endpoints:**
- `POST /api/crawl` - Trigger full crawl programmatically
- `GET /api/results/{spider}` - Get crawl results
- `GET /api/spiders` - List available spiders
- `GET /api/crawls/{id}/status` - Check crawl progress

**Technical:**
- FastAPI framework (async, fast, modern)
- API key authentication
- Rate limiting (prevent abuse)
- Basic error handling

**Why first:** Enables AI agents (OpenClaw, Claude Code, etc.) to integrate immediately. Single-article API validates core value prop before building marketplace infrastructure.

## Phase 1B: Spider Library (Q2 2026 - Month 2-3)

**Goal:** Make spiders shareable and reusable - multiply API value.

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

**For AI agents (OpenClaw, Claude Code, etc.):**
- Skip Phase 1-4 spider building
- Instant data access - load config, start scraping
- API + 100 spiders = scrape 100 sites programmatically
- No wasted compute on selector discovery

**Initial collection:** 50+ spiders for top news sites, e-commerce, job boards

### Spider Sharing & Publishing
- `./scrapai spiders publish <spider> --registry community`
- Markdown documentation template
- Example URLs and expected output
- License selection (MIT, Apache, CC0)

**Why after API:** API creates demand, library multiplies value. Early adopters use API with their spiders, then library makes API 10x more useful.

## Phase 2: Quality & Advanced API (Q3 2026)

**Goal:** Make it reliable and production-ready.

### Data Quality & Validation
**Problem:** Scraped data might be incomplete or wrong

**Features:**
- Schema validation (require fields: title, content, date)
- Quality scoring (completeness, content length)
- Anomaly detection (site changed, selectors broke)
- Auto-alerts (email, Slack, webhook) when spiders fail
- Validation reports per crawl

**Why:** Catch breakage early, maintain data integrity

### Advanced API Features
**Beyond Phase 1A basics:**
- **Webhooks** - Real-time notifications (crawl complete, spider failed)
- **WebSockets** - Live crawl progress updates
- **Batch operations** - Scrape multiple URLs in one request
- **OpenAPI/Swagger docs** - Interactive API documentation
- **Client libraries** - Python, JavaScript SDKs
- **Advanced auth** - OAuth, team management, usage analytics

**Why:** Phase 1A validates core API, Phase 2 adds production features based on real usage

## Contributing

**Want to help shape the roadmap?**

- **Discussions:** [GitHub Discussions](https://github.com/discourselab/scrapai-cli/discussions)
- **Feature requests:** [GitHub Issues](https://github.com/discourselab/scrapai-cli/issues)
- **Spider contributions:** Coming in Phase 1B (Spider Marketplace)

**Priority is driven by:**
1. Community feedback (what you actually need)
2. Production pain points (what breaks in real usage)
3. Ecosystem trends (AI agents, new anti-bot systems)

## Versioning

- **Current:** v0.1.0 (pre-1.0 alpha/beta)
- **v0.5.0 target:** Phase 1A complete (Minimal REST API)
- **v1.0.0 target:** Phase 1B complete (Spider Library + Marketplace)
- **v2.0.0 target:** Phase 2 complete (Quality/Validation + Advanced API)

Breaking changes expected until v1.0. We'll provide migration guides.

---

**Last updated:** March 2026
**Maintained by:** [DiscourseLab](https://www.discourselab.ai/)
