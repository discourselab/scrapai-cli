# scrapai CLI — Agent Rules (Cursor / Windsurf / Codex / Gemini / other agents)

**All agent instructions live in [`CLAUDE.md`](CLAUDE.md). Read that file — it is the single source of truth for every AI assistant.**

This file intentionally contains **no rules of its own**. Duplicating instructions here only causes drift: this file previously said "process one website at a time, sequential only, never parallel," which directly contradicted CLAUDE.md (it supports up to 5 in parallel). To prevent that, keep AGENTS.md a thin pointer and never add a rule, command, or principle here.
