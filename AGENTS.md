# ScrapAI CLI - Agent Rules (Cursor / Windsurf / Other Agents)

**For complete documentation, refer to: `CLAUDE.md`**

This file previously contained duplicate instructions. All agent guidance has been consolidated into CLAUDE.md to ensure consistency across all AI assistants (Claude Code, Cursor, Windsurf, Gemini, etc.).

## Quick Reference

Project-based Scrapy spider management for large-scale web scraping with database-first approach.

**Core Principles:**
- ✅ Process ONE website at a time (sequential only, never parallel)
- ✅ Follow 4-phase workflow: Analysis → Rules → Import → Test
- ✅ Complete ALL steps before marking status
- ✅ Use virtual environment: `source .venv/bin/activate && <command>`
- ✅ Run ONE command at a time (no chaining except venv activation)

**See CLAUDE.md for:**
- Complete workflow documentation (4 phases)
- Command execution rules
- Content focus guidelines
- Queue system usage
- CLI command reference
- Extractor configuration (newspaper, trafilatura, playwright)
- Playwright wait settings (for JS-delayed content)
- Status marking requirements
- Common pitfalls and solutions
