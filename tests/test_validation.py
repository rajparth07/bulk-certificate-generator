from app.validation import validate_recipient


def test_accepts_a_normal_recipient():
    assert validate_recipient("Ada Lovelace", "ada@example.com", "Track: API design") is None


def test_requires_a_name():
    assert validate_recipient("   ", None, None) == "Recipient name is required"


def test_rejects_a_name_without_letters():
    assert validate_recipient("12345", None, None) == "Recipient name must include letters"


def test_rejects_an_invalid_email_without_affecting_the_message_for_other_fields():
    message = validate_recipient("Ada Lovelace", "not-an-email", None)
    assert message == "Recipient email is not a valid email address"


def test_rejects_a_long_name():
    message = validate_recipient("A" * 121, None, None)
    assert message == "Recipient name must be at most 120 characters"


def test_rejects_a_long_detail():
    message = validate_recipient("Ada Lovelace", None, "d" * 201)
    assert message == "Recipient detail must be at most 200 characters"
