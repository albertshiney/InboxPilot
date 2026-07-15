"""Email classification using Anthropic Haiku model."""
from typing import Literal

from .config import get_settings
from .llm import get_anthropic

VALID_LABELS = {"support_request", "newsletter", "notification", "spam", "auto_reply"}


async def classify_email(
    subject: str, body: str
) -> Literal["support_request", "newsletter", "notification", "spam", "auto_reply"]:
    """
    Classify an email into one of five categories using Claude Haiku.

    Args:
        subject: Email subject line
        body: Email body content (will be truncated to 4000 chars)

    Returns:
        One of: support_request, newsletter, notification, spam, auto_reply
    """
    settings = get_settings()
    client = get_anthropic()

    # Truncate body to 4000 characters
    truncated_body = body[:4000]

    # Prepare the message
    user_message = f"""Please classify the following email into exactly one of these categories:
- support_request
- newsletter
- notification
- spam
- auto_reply

Subject: {subject}
Body: {truncated_body}

Respond with only the label, no other text."""

    try:
        response = await client.messages.create(
            model=settings.classify_model,
            max_tokens=10,
            temperature=0,
            system="You are an email classifier. Respond with only one of these labels: support_request, newsletter, notification, spam, auto_reply",
            messages=[{"role": "user", "content": user_message}],
        )

        # Extract the text from response
        result = response.content[0].text.strip().lower()

        # Validate and return
        if result in VALID_LABELS:
            return result  # type: ignore

        # Fall back to support_request for unknown/garbage output
        return "support_request"

    except Exception:
        # On any error, fail open to support_request
        return "support_request"
