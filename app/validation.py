"""Per-recipient checks. A failure here applies to one person, not the whole job."""

import re

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
NAME_EXTRA = set(" '-.")


def validate_recipient(name: str, email: str | None, detail: str | None) -> str | None:
    """Return an error message, or None when the recipient can be certified."""
    cleaned = (name or "").strip()
    if not cleaned:
        return "Recipient name is required"
    if len(cleaned) > 120:
        return "Recipient name must be at most 120 characters"
    if any(ord(character) < 32 for character in cleaned):
        return "Recipient name contains invalid characters"
    if not any(character.isalpha() for character in cleaned):
        return "Recipient name must include letters"
    if any(not (character.isalnum() or character in NAME_EXTRA) for character in cleaned):
        return "Recipient name contains invalid characters"

    if email:
        address = email.strip()
        if len(address) > 254 or EMAIL_RE.match(address) is None:
            return "Recipient email is not a valid email address"

    if detail and len(detail.strip()) > 200:
        return "Recipient detail must be at most 200 characters"
    return None
