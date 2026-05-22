import hashlib

from src.core.logic.pii_anonymizer import (
    PII_COLUMN_REGISTRY,
    anonymize_cpf,
    anonymize_email,
    anonymize_field,
    anonymize_person_data,
    is_anonymized_cpf,
    is_anonymized_email,
    scrub_emails_from_text,
    scrub_pii_deep,
    scrub_source_record_phones,
)

SALT = b":horizon-lgpd-v1"


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8") + SALT).hexdigest()


# --- anonymize_cpf ---


def test_anonymize_cpf_returns_lgpd_prefix():
    result = anonymize_cpf("12345678901")
    assert result.startswith("LGPD-")


def test_anonymize_cpf_deterministic():
    assert anonymize_cpf("12345678901") == anonymize_cpf("12345678901")


def test_anonymize_cpf_different_inputs_produce_different_hashes():
    assert anonymize_cpf("11111111111") != anonymize_cpf("22222222222")


def test_anonymize_cpf_correct_format():
    value = "12345678901"
    expected = f"LGPD-{_sha(value)[:16]}"
    assert anonymize_cpf(value) == expected


def test_anonymize_cpf_none_returns_none():
    assert anonymize_cpf(None) is None


def test_anonymize_cpf_empty_string_returns_none():
    assert anonymize_cpf("") is None


def test_anonymize_cpf_invalid_cpf_still_anonymized():
    result = anonymize_cpf("000.000.000-00")
    assert result is not None
    assert result.startswith("LGPD-")


# --- anonymize_email ---


def test_anonymize_email_returns_anon_lgpd_suffix():
    result = anonymize_email("user@example.com")
    assert result.endswith("@anon.lgpd")


def test_anonymize_email_deterministic():
    assert anonymize_email("user@example.com") == anonymize_email("user@example.com")


def test_anonymize_email_different_inputs_differ():
    assert anonymize_email("a@b.com") != anonymize_email("c@d.com")


def test_anonymize_email_correct_format():
    value = "user@example.com"
    expected = f"{_sha(value)[:12]}@anon.lgpd"
    assert anonymize_email(value) == expected


def test_anonymize_email_none_returns_none():
    assert anonymize_email(None) is None


def test_anonymize_email_empty_string_returns_none():
    assert anonymize_email("") is None


# --- anonymize_field ---


def test_anonymize_field_cpf():
    result = anonymize_field("12345678901", "cpf")
    assert result.startswith("LGPD-")


def test_anonymize_field_email():
    result = anonymize_field("user@example.com", "email")
    assert result.endswith("@anon.lgpd")


def test_anonymize_field_unknown_type_passthrough():
    assert anonymize_field("anything", "phone") == "anything"


# --- anonymize_person_data ---


def test_anonymize_person_data_masks_identification_id():
    result = anonymize_person_data(
        {"identification_id": "12345678901", "name": "Alice"}
    )
    assert result["identification_id"].startswith("LGPD-")
    assert result["name"] == "Alice"


def test_anonymize_person_data_masks_email():
    result = anonymize_person_data({"email": "alice@example.com"})
    assert result["email"].endswith("@anon.lgpd")


def test_anonymize_person_data_masks_contact_email():
    result = anonymize_person_data({"contact_email": "boss@example.com"})
    assert result["contact_email"].endswith("@anon.lgpd")


def test_anonymize_person_data_leaves_non_pii_keys_unchanged():
    data = {"name": "Alice", "campus": "Serra"}
    assert anonymize_person_data(data) == data


def test_anonymize_person_data_handles_none_pii_values():
    result = anonymize_person_data({"identification_id": None, "email": None})
    assert result["identification_id"] is None
    assert result["email"] is None


def test_anonymize_person_data_returns_new_dict():
    original = {"identification_id": "123"}
    result = anonymize_person_data(original)
    assert result is not original


def test_anonymize_person_data_all_registry_keys_masked():
    data = {col: "test-value" for col in PII_COLUMN_REGISTRY}
    result = anonymize_person_data(data)
    for col, field_type in PII_COLUMN_REGISTRY.items():
        if field_type == "cpf":
            assert result[col].startswith("LGPD-")
        elif field_type == "email":
            assert result[col].endswith("@anon.lgpd")


# --- is_anonymized_cpf ---


def test_is_anonymized_cpf_true_for_lgpd_prefix():
    assert is_anonymized_cpf("LGPD-abc123")


def test_is_anonymized_cpf_false_for_raw():
    assert not is_anonymized_cpf("12345678901")


def test_is_anonymized_cpf_false_for_none():
    assert not is_anonymized_cpf(None)


# --- is_anonymized_email ---


def test_is_anonymized_email_true_for_anon_lgpd():
    assert is_anonymized_email("abc123@anon.lgpd")


def test_is_anonymized_email_false_for_raw():
    assert not is_anonymized_email("user@example.com")


def test_is_anonymized_email_false_for_none():
    assert not is_anonymized_email(None)


# --- idempotency ---


def test_double_anonymize_cpf_is_idempotent():
    first = anonymize_cpf("12345678901")
    second = anonymize_cpf(first)
    assert first != second
    assert is_anonymized_cpf(first)


def test_anonymize_person_data_already_anonymized_cpf_still_hashes_again():
    anon = anonymize_cpf("12345678901")
    result = anonymize_person_data({"identification_id": anon})
    assert result["identification_id"].startswith("LGPD-")


# --- scrub_emails_from_text ---

def test_scrub_emails_from_text_replaces_email():
    result = scrub_emails_from_text("Contact: user@example.com for details.")
    assert "user@example.com" not in result
    assert "@anon.lgpd" in result


def test_scrub_emails_from_text_replaces_multiple_emails():
    text = "a@b.com and c@d.com"
    result = scrub_emails_from_text(text)
    assert "a@b.com" not in result
    assert "c@d.com" not in result
    assert result.count("@anon.lgpd") == 2


def test_scrub_emails_from_text_preserves_anon_lgpd():
    text = "already abc123456789@anon.lgpd done"
    assert scrub_emails_from_text(text) == text


def test_scrub_emails_from_text_no_email_unchanged():
    text = "nothing to scrub here"
    assert scrub_emails_from_text(text) == text


def test_scrub_emails_from_text_none_returns_none():
    assert scrub_emails_from_text(None) is None


def test_scrub_emails_from_text_lideres_pattern():
    text = " Carlos Campos (carlosr@ifes.edu.br), Maria Alice (mariaalice@ifes.edu.br)"
    result = scrub_emails_from_text(text)
    assert "carlosr@ifes.edu.br" not in result
    assert "mariaalice@ifes.edu.br" not in result
    assert "Carlos Campos" in result
    assert "Maria Alice" in result


# --- scrub_pii_deep ---

def test_scrub_pii_deep_string():
    result = scrub_pii_deep("email: foo@bar.com")
    assert "foo@bar.com" not in result
    assert "@anon.lgpd" in result


def test_scrub_pii_deep_dict():
    data = {"OrientadorEmail": "prof@ifes.edu.br", "name": "João"}
    result = scrub_pii_deep(data)
    assert "prof@ifes.edu.br" not in result["OrientadorEmail"]
    assert result["OrientadorEmail"].endswith("@anon.lgpd")
    assert result["name"] == "João"


def test_scrub_pii_deep_nested_dict():
    data = {"changes": [{"after": '{"resume": "bio text user@x.com end"}'}]}
    result = scrub_pii_deep(data)
    assert "user@x.com" not in result["changes"][0]["after"]
    assert "@anon.lgpd" in result["changes"][0]["after"]


def test_scrub_pii_deep_list():
    data = ["a@b.com", "no email", "c@d.com"]
    result = scrub_pii_deep(data)
    assert all("@anon.lgpd" in r or r == "no email" for r in result)


def test_scrub_pii_deep_non_string_passthrough():
    assert scrub_pii_deep(42) == 42
    assert scrub_pii_deep(None) is None
    assert scrub_pii_deep(3.14) == 3.14


def test_scrub_pii_deep_preserves_anon_lgpd():
    data = {"email": "abc123456789@anon.lgpd"}
    assert scrub_pii_deep(data) == data


# --- scrub_source_record_phones ---

def test_scrub_source_record_phones_nulls_celular_orientador():
    payload = {"CelularOrientador": "27988281460", "name": "Test"}
    result = scrub_source_record_phones(payload)
    assert result["CelularOrientador"] is None
    assert result["name"] == "Test"


def test_scrub_source_record_phones_nulls_celular_orientado():
    payload = {"CelularOrientado": "27999215433"}
    result = scrub_source_record_phones(payload)
    assert result["CelularOrientado"] is None


def test_scrub_source_record_phones_missing_fields_safe():
    payload = {"OrientadorEmail": "x@anon.lgpd"}
    result = scrub_source_record_phones(payload)
    assert result == payload


def test_scrub_source_record_phones_returns_new_dict():
    payload = {"CelularOrientador": "123"}
    result = scrub_source_record_phones(payload)
    assert result is not payload
