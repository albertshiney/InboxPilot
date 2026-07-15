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
