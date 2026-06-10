import hashlib
import re
from typing import Any

SALT = b":horizon-lgpd-v1"

PII_COLUMN_REGISTRY: dict[str, str] = {
    "identification_id": "cpf",
    "email": "email",
    "contact_email": "email",
}

# Structured phone fields in SigPesq advisorship payloads — nulled on export.
_PAYLOAD_PHONE_FIELDS = frozenset({"CelularOrientador", "CelularOrientado"})

_EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@(?!anon\.lgpd)[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
)


def anonymize_cpf(value: str | None) -> str | None:
    if not value:
        return None
    digest = hashlib.sha256(value.encode("utf-8") + SALT).hexdigest()
    return f"LGPD-{digest[:16]}"


def anonymize_email(value: str | None) -> str | None:
    if not value:
        return None
    digest = hashlib.sha256(value.encode("utf-8") + SALT).hexdigest()
    return f"{digest[:12]}@anon.lgpd"


def anonymize_field(value: str | None, field_type: str) -> str | None:
    if field_type == "cpf":
        return anonymize_cpf(value)
    if field_type == "email":
        return anonymize_email(value)
    return value


def anonymize_person_data(data: dict) -> dict:
    result = dict(data)
    for column, field_type in PII_COLUMN_REGISTRY.items():
        if column in result:
            result[column] = anonymize_field(result[column], field_type)
    return result


def scrub_emails_from_text(text: str | None) -> str | None:
    """Replace every real email address in a free-text string with its anonymized hash."""
    if not text:
        return text
    return _EMAIL_RE.sub(lambda m: anonymize_email(m.group(0)), text)


def scrub_pii_deep(value: Any) -> Any:
    """Recursively anonymize email addresses in any JSON-serializable value."""
    if isinstance(value, str):
        return scrub_emails_from_text(value)
    if isinstance(value, dict):
        return {k: scrub_pii_deep(v) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub_pii_deep(v) for v in value]
    return value


def scrub_source_record_phones(payload: dict) -> dict:
    """Null out phone number fields in a source record payload dict."""
    result = dict(payload)
    for field in _PAYLOAD_PHONE_FIELDS:
        if field in result:
            result[field] = None
    return result


def is_anonymized_cpf(value: str | None) -> bool:
    return bool(value and value.startswith("LGPD-"))


def is_anonymized_email(value: str | None) -> bool:
    return bool(value and value.endswith("@anon.lgpd"))
