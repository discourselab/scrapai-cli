"""LLM-based analysis of inspect output."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from generate.llm_client import LLMClient
from generate.prompt_guidance import AGENT_SYSTEM_INSTRUCTIONS

logger = logging.getLogger(__name__)


class AnalysisSchema(BaseModel):
    model_config = ConfigDict(extra="allow")

    content_type: str = Field(..., description="High-level content type")
    extraction_strategy: str = Field(
        ..., description="Recommended extraction strategy"
    )
    url_patterns: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="URL pattern groups like listing/detail/article",
    )
    callback_names: List[str] = Field(
        default_factory=list, description="Suggested callback names"
    )
    selector_hints: Dict[str, str] = Field(
        default_factory=dict, description="Selector hints if needed"
    )
    notes: Optional[str] = Field(default=None)


def _build_messages(inspect_summary: Dict[str, Any], description: str) -> List[Dict[str, str]]:
    schema_json = json.dumps(AnalysisSchema.model_json_schema(), indent=2)
    summary_json = json.dumps(inspect_summary, indent=2)

    system = (
        AGENT_SYSTEM_INSTRUCTIONS
        + "You are a web scraping analyst. "
        "Return only valid JSON matching the provided schema. "
        "No markdown, no explanations."
    )

    user = (
        "Analyze the site based on the inspect summary and extraction goal.\n\n"
        "Extraction goal:\n"
        f"{description}\n\n"
        "Inspect summary (HTML snapshot, selectors, URL samples, JS signals):\n"
        f"{summary_json}\n\n"
        "Output JSON schema:\n"
        f"{schema_json}\n\n"
        "Rules:\n"
        "- Output only valid JSON matching the schema.\n"
        "- Use only selectors present in the inspect summary.\n"
        "- Be concise but specific about URL patterns and extraction strategy.\n"
    )

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _format_validation_error(err: ValidationError) -> str:
    parts = []
    for e in err.errors():
        loc = " -> ".join(str(x) for x in e.get("loc", []))
        msg = e.get("msg", "Invalid value")
        parts.append(f"{loc}: {msg}")
    return "; ".join(parts)


async def analyze_site(
    client: LLMClient,
    inspect_summary: Dict[str, Any],
    description: str,
    max_retries: int = 3,
) -> Dict[str, Any]:
    messages = _build_messages(inspect_summary, description)

    for attempt in range(1, max_retries + 1):
        content = await client.complete(messages, structured_output=True)
        try:
            data = json.loads(content)
            validated = AnalysisSchema(**data)
            return validated.model_dump()
        except (json.JSONDecodeError, ValidationError) as exc:
            if attempt >= max_retries:
                raise
            if isinstance(exc, ValidationError):
                error_msg = _format_validation_error(exc)
            else:
                error_msg = f"Invalid JSON: {exc}"
            logger.debug("Analysis validation failed, retrying: %s", error_msg)
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "The previous JSON did not validate. "
                        f"Errors: {error_msg}. "
                        "Please output a corrected JSON object only."
                    ),
                }
            )

    raise RuntimeError("Analysis retries exhausted")
