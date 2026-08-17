from unittest.mock import MagicMock, patch

import pytest

from src.core.logic.person_matcher import PersonMatcher


class MockPerson:
    def __init__(self, id, name, identification_id=None, email=None):
        self.id = id
        self.name = name
        self.identification_id = identification_id
        self.email = email


@pytest.fixture
def matcher():
    controller = MagicMock()
    return PersonMatcher(controller)


def test_normalize_name(matcher):
    assert matcher.normalize_name("Pãulo Sérgio Junior") == "PAULO SERGIO JUNIOR"
    assert matcher.normalize_name("  ROBERTO   CARLOS  ") == "ROBERTO CARLOS"
    assert matcher.normalize_name("") == ""


def test_canonicalize_name_normalizes_particles(matcher):
    assert (
        matcher.canonicalize_name("Gustavo Maia De Almeida")
        == "GUSTAVO MAIA de ALMEIDA"
    )
    assert (
        matcher.canonicalize_name("Gustavo Maia de Almeida")
        == "GUSTAVO MAIA de ALMEIDA"
    )


def test_match_or_create_exact(matcher):
    person = MockPerson(1, "Paulo Sergio")
    matcher.person_controller.get_all.return_value = [person]
    matcher.preload_cache()

    result = matcher.match_or_create("Paulo Sergio")
    assert result.id == 1
    matcher.person_controller.create_person.assert_not_called()


def test_match_or_create_fuzzy(matcher):
    person_a = MockPerson(1, "Persona A Alpha")
    matcher.person_controller.get_all.return_value = [person_a]
    matcher.preload_cache()

    # 1. Fuzzy match (score >= 90)
    result = matcher.match_or_create("Persona Alpha", strict_match=False)
    assert result.id == 1

    # 2. Strict match with DIFFERENT name to avoid cache hit
    # and force it to check the fuzzy matching list
    new_p = MockPerson(2, "Persona Beta")
    matcher.person_controller.create_person.return_value = new_p

    # "Persona Beta" vs "Persona A Alpha" will have low score
    result = matcher.match_or_create("Persona Beta", strict_match=True)
    assert result.id == 2
    assert result.name == "Persona Beta"


def test_strict_match_avoids_fuzzy(matcher):
    person_a = MockPerson(1, "Jose Silva")
    matcher.person_controller.get_all.return_value = [person_a]
    matcher.preload_cache()

    # Jose da Silva vs Jose Silva is high score (~90) but not 100
    new_p = MockPerson(2, "Jose da Silva")
    matcher.person_controller.create_person.return_value = new_p

    # With strict_match=True, it should NOT match "Jose Silva" and should CREATE "Jose da Silva"
    result = matcher.match_or_create("Jose da Silva", strict_match=True)
    assert result.id == 2
    matcher.person_controller.create_person.assert_called()


def test_match_or_create_uses_canonical_name_for_case_variants(matcher):
    person = MockPerson(1, "Gustavo Maia de Almeida")
    matcher.person_controller.get_all.return_value = [person]
    matcher.preload_cache()

    result = matcher.match_or_create("Gustavo Maia De Almeida", strict_match=True)
    assert result.id == 1
    matcher.person_controller.create_person.assert_not_called()


def test_repeated_fuzzy_variant_reuses_normalized_cache_without_refuzzing(matcher):
    """Perf regression guard: once a name variant has been fuzzy-matched, an
    identical repeat lookup must hit the O(1) normalized-cache path (step 2)
    instead of re-running thefuzz.process.extractOne — this is what makes
    repeated misspellings across many records cheap instead of re-scanning
    the whole cache with fuzzy matching every time."""
    person_a = MockPerson(1, "Persona A Alpha")
    matcher.person_controller.get_all.return_value = [person_a]
    matcher.preload_cache()

    first = matcher.match_or_create("Persona Alpha", strict_match=False)
    assert first.id == 1
    assert matcher.normalize_name("Persona Alpha") in matcher._normalized_cache

    with patch("src.core.logic.person_matcher.process.extractOne") as mock_extract_one:
        second = matcher.match_or_create("Persona Alpha", strict_match=False)
        assert second.id == 1
        mock_extract_one.assert_not_called()


def test_normalized_cache_stays_consistent_with_persons_cache_after_preload(matcher):
    """Every person with a non-empty normalized name must be indexed in
    _normalized_cache after preload, keeping step 2's O(1) lookup complete."""
    person = MockPerson(1, "Ana Beatriz Souza")
    matcher.person_controller.get_all.return_value = [person]
    matcher.preload_cache()

    assert (
        matcher._normalized_cache[matcher.normalize_name("Ana Beatriz Souza")].id == 1
    )


def test_match_or_create_prefers_richer_duplicate_for_same_canonical_name(matcher):
    duplicate_plain = MockPerson(1, "Paulo Sérgio Dos Santos Júnior")
    duplicate_rich = MockPerson(
        2,
        "Paulo Sergio dos Santos Junior",
        identification_id="8400407353673370",
    )
    matcher.person_controller.get_all.return_value = [duplicate_plain, duplicate_rich]
    matcher.preload_cache()

    result = matcher.match_or_create(
        "Paulo Sérgio dos Santos Júnior", strict_match=True
    )
    assert result.id == 2
    matcher.person_controller.create_person.assert_not_called()
