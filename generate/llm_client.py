"""OpenAI-compatible async LLM client with structured output fallback."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(self, api_base: str, api_key: str, model: str, timeout: int = 30):
        self.model = model
        self._timeout = timeout
        self._client = AsyncOpenAI(api_key=api_key, base_url=api_base)

    async def complete(
        self, messages: List[Dict[str, Any]], structured_output: bool = True
    ) -> str:
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "timeout": self._timeout,
        }
        if structured_output:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            response = await self._client.chat.completions.create(**kwargs)
            content = _extract_response_content(response)
            if not structured_output:
                content = _extract_json_from_text(content)
            return content
        except Exception as exc:
            if structured_output and _response_format_unsupported(exc):
                logger.debug(
                    "response_format unsupported by endpoint; retrying without it"
                )
                return await self.complete(messages, structured_output=False)
            raise


def _extract_response_content(response: Any) -> str:
    if isinstance(response, str):
        return response

    choice = None
    if isinstance(response, dict):
        choices = response.get("choices") or []
        if choices:
            choice = choices[0]
    else:
        choices = getattr(response, "choices", None)
        if choices:
            choice = choices[0]

    if not choice:
        raise ValueError("LLM response had no choices")

    if isinstance(choice, dict):
        msg = choice.get("message") or {}
        if isinstance(msg, dict):
            return msg.get("content", "")
        return str(msg)

    message = getattr(choice, "message", None)
    if isinstance(message, str):
        return message
    return getattr(message, "content", "")


def _response_format_unsupported(exc: Exception) -> bool:
    message = str(exc).lower()
    return "response_format" in message or "response format" in message


def _extract_json_from_text(text: str) -> str:
    """Extract the first JSON object from a text response."""
    if not text:
        raise ValueError("Empty LLM response")

    cleaned = text.strip()

    # Strip markdown fences if present
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if len(lines) >= 3 and lines[0].startswith("```") and lines[-1].startswith("```"):
            cleaned = "\n".join(lines[1:-1]).strip()

    start = cleaned.find("{")
    if start == -1:
        raise ValueError("No JSON object found in LLM response")

    decoder = json.JSONDecoder()
    obj, _ = decoder.raw_decode(cleaned[start:])
    return json.dumps(obj)
