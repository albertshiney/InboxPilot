"""Sonnet-based reply drafting.

`generate_draft` is the single Anthropic call that produces a candidate
customer-support reply. The model is asked to respond with JSON only; real
model output sometimes wraps that JSON in a markdown code fence or adds a
little prose, so `_extract_json` is a tolerant extractor (strip fences,
then take the first `{` through the last `}`) rather than a strict
`json.loads` on the raw text. If extraction/parsing fails outright, or the
model answered in prose instead of JSON, we fail safe into a fallback
`DraftResult` that always requires human review.
"""

import json
import re
from typing import Any

from pydantic import BaseModel, field_validator

from .config import get_settings
from .llm import get_anthropic

FALLBACK_ACK_TEXT = (
    "Thanks for reaching out — I'll check with the team and get back to you shortly."
)

HARD_RULES = (
    "Only answer from the provided context. If the context does not contain "
    "the answer, say you'll check with the team and set requires_human to true."
)

_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


class DraftResult(BaseModel):
    """Canonical shape returned by `generate_draft`, independent of how the
    model's raw text was parsed."""

    reply: str
    confidence: int
    category: str
    requires_human: bool
    reasoning: str
    sources_used: list[str] = []

    @field_validator("confidence")
    @classmethod
    def _clamp_confidence(cls, value: int) -> int:
        return max(0, min(100, value))


def _fallback(reasoning: str = "model output unparseable") -> DraftResult:
    return DraftResult(
        reply=FALLBACK_ACK_TEXT,
        confidence=0,
        category="other",
        requires_human=True,
        reasoning=reasoning,
        sources_used=[],
    )


def _build_system_prompt(workspace: dict, settings: dict) -> str:
    name = workspace.get("name") or "the company"
    tone = settings.get("tone", "friendly")
    signature = settings.get("signature", "")
    custom_instructions = settings.get("customInstructions", "")

    return (
        f"You are drafting an email reply on behalf of {name}, a company that "
        "handles customer support over email.\n\n"
        f"Tone: {tone}.\n"
        f"Signature to close the email with: {signature}\n"
        f"Additional instructions from the workspace owner: {custom_instructions}\n\n"
        f"{HARD_RULES}\n\n"
        "Respond with JSON only, no prose before or after, in exactly this shape:\n"
        '{"reply": "<the drafted reply text>", "confidence": <int 0-100>, '
        '"category": "<short category label>", "requires_human": <true|false>, '
        '"reasoning": "<brief internal reasoning>", "sources_used": ["<documentName>", ...]}'
    )


def _build_user_content(thread_messages: list[dict], kb_chunks: list[dict]) -> str:
    lines = ["Email thread history (oldest first, newest last):"]
    if not thread_messages:
        lines.append("(no prior messages)")
    for m in thread_messages:
        sender = m.get("from") or m.get("from_") or m.get("sentBy") or "unknown"
        lines.append(f"- {sender}: {m.get('bodyText', '')}")

    lines.append("\nKnowledge base context (numbered, cite by documentName in sources_used):")
    if not kb_chunks:
        lines.append("(no relevant context was found)")
    else:
        for i, chunk in enumerate(kb_chunks, start=1):
            lines.append(f"[{i}] documentName={chunk.get('documentName')}: {chunk.get('text')}")

    return "\n".join(lines)


def _extract_json(text: str) -> dict[str, Any] | None:
    """Strip a surrounding markdown code fence if present, then take the
    substring from the first `{` to the last `}` and try to parse it as
    JSON. Returns `None` if no JSON object can be found/parsed."""
    stripped = text.strip()

    fence_match = _CODE_FENCE_RE.search(stripped)
    if fence_match:
        stripped = fence_match.group(1).strip()

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None

    candidate = stripped[start : end + 1]
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None

    if not isinstance(parsed, dict):
        return None
    return parsed


async def generate_draft(
    workspace: dict, thread_messages: list[dict], kb_chunks: list[dict]
) -> DraftResult:
    """Make one Sonnet call to draft a reply, given the workspace's tone /
    signature / custom instructions, the thread history, and retrieved KB
    chunks. Always returns a `DraftResult` — parse failures fail safe into
    a fallback that requires human review rather than raising."""
    settings = workspace.get("settings") or {}
    system_prompt = _build_system_prompt(workspace, settings)
    user_content = _build_user_content(thread_messages, kb_chunks)

    client = get_anthropic()
    response = await client.messages.create(
        model=get_settings().draft_model,
        max_tokens=1500,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
    )

    text = response.content[0].text
    parsed = _extract_json(text)
    if parsed is None:
        return _fallback()

    try:
        return DraftResult(
            reply=parsed["reply"],
            confidence=int(parsed.get("confidence", 0)),
            category=parsed.get("category") or "other",
            requires_human=bool(parsed.get("requires_human", False)),
            reasoning=parsed.get("reasoning", ""),
            sources_used=list(parsed.get("sources_used") or []),
        )
    except (KeyError, TypeError, ValueError):
        return _fallback()
