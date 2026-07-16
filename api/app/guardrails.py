"""Pure guardrail checks that gate autopilot auto-send.

`check` never touches the database or the network — it takes everything it
needs as arguments and returns the list of violated rule names (empty list
== safe to auto-send). Keeping it pure makes every rule independently
testable and keeps `pipeline.py`'s orchestration logic simple: autopilot
fires iff autopilot is on, confidence clears the threshold, and this
function returns `[]`.
"""

import re

from .draft import DraftResult

DEFAULT_BLOCKED_CATEGORIES = ["refund"]

# Case-insensitive: any of these phrases anywhere in the inbound message
# text is treated as a signal the customer is already escalating, so a
# human should be the one replying.
_ESCALATION_PATTERN = re.compile(
    r"\b(lawyer|legal|sue|lawsuit|chargeback|attorney|scam|fraud|furious|unacceptable)\b|report you",
    re.IGNORECASE,
)

# Prompt-injection markers that may appear in untrusted inbound email text.
# Compared case-insensitively as plain substrings (dependency-free). Any hit
# means the inbound message is trying to manipulate the drafting model, so the
# reply must never be auto-sent — it goes to a human regardless of the model's
# self-reported confidence.
_INJECTION_MARKERS = (
    "ignore previous",
    "ignore all previous",
    "disregard",
    "system prompt",
    "your instructions",
    "verbatim",
    "reveal",
    "assistant:",
    "system:",
)

# A reply that reproduces a verbatim span at least this long from a KB chunk or
# the system prompt is treated as exfiltration and blocked from auto-send.
REPLY_SCREEN_MIN_SPAN = 200


def _has_long_shared_span(source: str, reply: str, min_len: int = REPLY_SCREEN_MIN_SPAN) -> bool:
    """Return True if `reply` contains any verbatim substring of `source` at
    least `min_len` characters long. Pure string ops, no dependencies."""
    source = source or ""
    reply = reply or ""
    if len(source) < min_len or len(reply) < min_len:
        return False
    for i in range(0, len(source) - min_len + 1):
        if source[i : i + min_len] in reply:
            return True
    return False


def screen_reply(
    *,
    reply_text: str,
    inbound_text: str,
    kb_chunks: list[dict] | None = None,
    system_prompt: str | None = None,
) -> list[str]:
    """Independent reply-screening guardrail for the autopilot path.

    Inspects the generated reply and the untrusted inbound email WITHOUT
    trusting the model's self-reported confidence. Returns violated rule
    names:
      - "prompt_injection": the inbound email contains a prompt-injection
        marker (case-insensitive).
      - "kb_exfiltration": the reply reproduces a long verbatim span
        (>= REPLY_SCREEN_MIN_SPAN chars) of a provided KB chunk or the
        system prompt.
    An empty list means the reply cleared this screen.
    """
    violations: list[str] = []

    lowered = (inbound_text or "").lower()
    if any(marker in lowered for marker in _INJECTION_MARKERS):
        violations.append("prompt_injection")

    sources = [chunk.get("text", "") for chunk in (kb_chunks or [])]
    if system_prompt:
        sources.append(system_prompt)
    if any(_has_long_shared_span(src, reply_text or "") for src in sources):
        violations.append("kb_exfiltration")

    return violations


def check(
    draft: DraftResult,
    *,
    settings: dict,
    chunks_found: bool,
    inbound_text: str,
    prior_ai_reply_in_thread: bool,
    sender: str,
    blocked_senders: list[str],
) -> list[str]:
    """Return the list of violated guardrail rule names for `draft`. An
    empty list means nothing fired and autopilot may proceed (subject to
    the caller's own autopilot/confidence checks)."""
    violations: list[str] = []

    if draft.requires_human:
        violations.append("requires_human")

    blocked_categories = settings.get("blockedCategories", DEFAULT_BLOCKED_CATEGORIES)
    if draft.category in blocked_categories:
        violations.append("blocked_category")

    if not chunks_found:
        violations.append("no_kb_context")

    if _ESCALATION_PATTERN.search(inbound_text or ""):
        violations.append("escalation_language")

    if prior_ai_reply_in_thread:
        violations.append("loop_prevention")

    if sender in (blocked_senders or []):
        violations.append("blocked_sender")

    return violations
