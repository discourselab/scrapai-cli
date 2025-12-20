---
trigger: always_on
---

# ScrapAI Agent Rules (Google Gemini)

**For complete documentation, refer to: `/CLAUDE.md`**

This file previously contained duplicate instructions. All agent guidance has been consolidated into CLAUDE.md to ensure consistency across all AI assistants (Claude Code, Cursor, Gemini, etc.).

## Quick Reference

Project-based Scrapy spider management for large-scale web scraping with database-first approach.

**Key Rules:**
- ✅ Process ONE website at a time (sequential only, never parallel)
- ✅ Follow 4-phase workflow: Analysis → Rules → Import → Test
- ✅ Complete ALL steps before marking status
- ✅ Use virtual environment: `source .venv/bin/activate && <command>`

**See CLAUDE.md for:**
- Complete workflow documentation
- Command execution rules
- Content focus guidelines
- Queue system usage
- CLI reference
- Extractor configuration
- Playwright wait settings
