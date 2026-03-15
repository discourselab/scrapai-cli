"""Shared instructions derived from CLAUDE.md / AGENTS.md for prompts."""

AGENT_SYSTEM_INSTRUCTIONS = (
    "Follow the ScrapAI CLI workflow described in CLAUDE.md and AGENTS.md: "
    "Always run inspect → analyze → generate → validate in order, never skip phases, and keep every command project-scoped. "
    "Treat the spider as database-first: document selectors/URL patterns during inspection, keep callbacks disciplined, and validate every JSON against SpiderConfigSchema before any DB import. "
    "Never invent new dependencies or system changes; stay within the existing extractor/custom selector approach and follow the standard safety rules (no parallel phase execution, no manual HTML editing, no new database engines). "
)
