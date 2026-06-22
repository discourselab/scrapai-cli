# scrapai CLI - Agent Rules (Cursor / Windsurf / Other Agents)

**For complete documentation, refer to: `CLAUDE.md`**

This file previously contained duplicate instructions. All agent guidance has been consolidated into CLAUDE.md to ensure consistency across all AI assistants (Claude Code, Cursor, Windsurf, Gemini, etc.).

## Quick Reference

Project-based Scrapy spider management for large-scale web scraping with database-first approach.

**Core Principles:**
- ✅ Process ONE website at a time (sequential only, never parallel)
- ✅ Follow 4-phase workflow: Analysis → Rules → Import → Test
- ✅ Complete ALL steps before marking status
- ✅ Run commands directly: `./scrapai <command>` (venv activation is automatic)
- ✅ Run ONE command at a time (no chaining)

**See CLAUDE.md for:**
- Complete workflow documentation (4 phases)
- Command execution rules
- Content focus guidelines
- Queue system usage
- CLI command reference
- Extractor configuration (trafilatura, newspaper, playwright)
- Playwright wait settings (for JS-delayed content)
- Status marking requirements
- Common pitfalls and solutions

<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:7510c1e2 -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

**Architecture in one line:** issues live in a local Dolt DB; sync uses `refs/dolt/data` on your git remote; `.beads/issues.jsonl` is a passive export. See https://github.com/gastownhall/beads/blob/main/docs/SYNC_CONCEPTS.md for details and anti-patterns.

## Session Completion

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds
<!-- END BEADS INTEGRATION -->
