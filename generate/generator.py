"""LLM-based spider config generator."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from pydantic import ValidationError

from core.schemas import SpiderConfigSchema
from generate.llm_client import LLMClient

logger = logging.getLogger(__name__)


def _build_messages(
    inspect_summary: Dict[str, Any],
    analysis: Dict[str, Any],
    description: str,
    examples: List[Dict[str, Any]],
) -> List[Dict[str, str]]:
    schema_json = json.dumps(SpiderConfigSchema.model_json_schema(), indent=2)
    summary_json = json.dumps(inspect_summary, indent=2)
    analysis_json = json.dumps(analysis, indent=2)
    examples_json = json.dumps(examples, indent=2)

    system = (
        "You are an expert web scraping engineer. "
        "Return only valid JSON matching the provided schema. "
        "No markdown, no explanations, no code fences."
    )

    user = (
        "Generate a ScrapAI spider configuration JSON.\n\n"
        "Extraction goal:\n"
        f"{description}\n\n"
        "Inspect summary (HTML snapshot, selectors, URL samples, JS signals):\n"
        f"{summary_json}\n\n"
        "Analysis output:\n"
        f"{analysis_json}\n\n"
        "SpiderConfig JSON schema:\n"
        f"{schema_json}\n\n"
        "Example spider configs:\n"
        f"{examples_json}\n\n"
        "Rules:\n"
        "- Output only valid JSON.\n"
        "- Populate all required fields.\n"
        "- Use only selectors confirmed in the inspect summary.\n"
        "- Prefer parse_article for article-style content unless custom callbacks are needed.\n"
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


def _normalize_config(
    data: Dict[str, Any], name: str, source_url: str, allowed_domain: str
) -> Dict[str, Any]:
    normalized = dict(data)
    normalized["name"] = name
    normalized["source_url"] = source_url

    allowed_domains = normalized.get("allowed_domains")
    if isinstance(allowed_domains, str):
        allowed_domains = [allowed_domains]
    if not allowed_domains:
        allowed_domains = [allowed_domain]
    elif allowed_domain not in allowed_domains:
        allowed_domains = [allowed_domain] + list(allowed_domains)
    normalized["allowed_domains"] = allowed_domains

    start_urls = normalized.get("start_urls")
    if isinstance(start_urls, str):
        start_urls = [start_urls]
    if not start_urls:
        normalized["start_urls"] = [source_url]

    return normalized


async def generate_config(
    client: LLMClient,
    inspect_summary: Dict[str, Any],
    analysis: Dict[str, Any],
    description: str,
    examples: List[Dict[str, Any]],
    name: str,
    source_url: str,
    allowed_domain: str,
    max_retries: int = 3,
) -> Dict[str, Any]:
    messages = _build_messages(inspect_summary, analysis, description, examples)

    for attempt in range(1, max_retries + 1):
        content = await client.complete(messages, structured_output=True)
        try:
            data = json.loads(content)
            normalized = _normalize_config(data, name, source_url, allowed_domain)
            validated = SpiderConfigSchema(**normalized)
            return validated.model_dump(exclude_none=True)
        except (json.JSONDecodeError, ValidationError) as exc:
            if attempt >= max_retries:
                raise
            if isinstance(exc, ValidationError):
                error_msg = _format_validation_error(exc)
            else:
                error_msg = f"Invalid JSON: {exc}"
            logger.debug("Generation validation failed, retrying: %s", error_msg)
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

    raise RuntimeError("Generator retries exhausted")
