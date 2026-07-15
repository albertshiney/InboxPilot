"""Tests for the pure guardrail-check function."""
from app.draft import DraftResult
from app import guardrails


def _draft(**overrides) -> DraftResult:
    base = dict(
        reply="Here is the answer.",
        confidence=90,
        category="general",
        requires_human=False,
        reasoning="looks good",
        sources_used=["doc1.txt"],
    )
    base.update(overrides)
    return DraftResult(**base)


def _settings(**overrides) -> dict:
    base = dict(
        autopilot=True,
        confidenceThreshold=85,
        tone="friendly",
        signature="",
        blockedCategories=["refund"],
        customInstructions="",
    )
    base.update(overrides)
    return base


def _check(draft=None, **overrides):
    kwargs = dict(
        settings=_settings(),
        chunks_found=True,
        inbound_text="Hi, when will my order arrive?",
        prior_ai_reply_in_thread=False,
        sender="customer@example.com",
        blocked_senders=[],
    )
    kwargs.update(overrides)
    return guardrails.check(draft or _draft(), **kwargs)


def test_no_violations_when_everything_is_clean():
    assert _check() == []


def test_requires_human_fires():
    violations = _check(_draft(requires_human=True))
    assert "requires_human" in violations


def test_blocked_category_fires_for_refund_by_default():
    violations = _check(_draft(category="refund"))
    assert "blocked_category" in violations


def test_blocked_category_does_not_fire_for_allowed_category():
    violations = _check(_draft(category="general"))
    assert "blocked_category" not in violations


def test_no_kb_context_fires_when_no_chunks_found():
    violations = _check(chunks_found=False)
    assert "no_kb_context" in violations


def test_escalation_language_fires_on_lawyer_mention():
    violations = _check(inbound_text="I'm going to talk to my lawyer about this.")
    assert "escalation_language" in violations


def test_escalation_language_fires_case_insensitively_on_chargeback():
    violations = _check(inbound_text="I will file a CHARGEBACK if this isn't fixed.")
    assert "escalation_language" in violations


def test_escalation_language_does_not_fire_on_clean_text():
    violations = _check(inbound_text="Just checking on my order status, thanks!")
    assert "escalation_language" not in violations


def test_escalation_language_does_not_fire_on_issue_substring_of_sue():
    """Regression: the old unanchored regex matched "sue" as a substring of
    "issue", which meant nearly every support email ("I have an issue...")
    tripped the escalation guardrail and quietly disabled autopilot."""
    violations = _check(inbound_text="I have an issue with my order, can you help?")
    assert "escalation_language" not in violations


def test_escalation_language_fires_on_sue_as_a_whole_word():
    violations = _check(inbound_text="I will sue you if this isn't fixed.")
    assert "escalation_language" in violations


def test_loop_prevention_fires_when_prior_ai_reply_in_thread():
    violations = _check(prior_ai_reply_in_thread=True)
    assert "loop_prevention" in violations


def test_blocked_sender_fires_when_sender_in_blocked_list():
    violations = _check(sender="spammer@bad.com", blocked_senders=["spammer@bad.com"])
    assert "blocked_sender" in violations


def test_blocked_sender_does_not_fire_when_sender_not_blocked():
    violations = _check(sender="customer@example.com", blocked_senders=["spammer@bad.com"])
    assert "blocked_sender" not in violations


def test_multiple_violations_can_fire_together():
    violations = _check(
        _draft(requires_human=True, category="refund"),
        chunks_found=False,
        prior_ai_reply_in_thread=True,
    )
    assert set(violations) == {
        "requires_human",
        "blocked_category",
        "no_kb_context",
        "loop_prevention",
    }
