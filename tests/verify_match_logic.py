import re
import unicodedata
from typing import Dict, Optional

from thefuzz import fuzz, process


class MockPerson:

    def __init__(self, id, name):
        self.id = id
        self.name = name


def normalize_name(name: str) -> str:
    if not name:
        return ""
    name_str = "".join(
        c for c in unicodedata.normalize("NFD", name) if unicodedata.category(c) != "Mn"
    )
    name_str = re.sub(r"[^A-Z\s]", " ", name_str.upper())
    return " ".join(name_str.split())


def get_person(name: str, cache: Dict[str, MockPerson]) -> Optional[MockPerson]:
    if not name or not name.strip():
        return None
    name = name.strip()
    normalized_input = normalize_name(name)

    # 1. Exact Match (Normalized)
    for cached_name, person in cache.items():
        if normalize_name(cached_name) == normalized_input:
            print(f"DEBUG: Exact match (normalized) for '{name}': '{cached_name}'")
            return person

    # 2. Fuzzy Matching
    names_in_cache = list(cache.keys())
    if names_in_cache:
        normalized_to_original = {normalize_name(n): n for n in names_in_cache}
        normalized_list = list(normalized_to_original.keys())
        best_norm_match, score = process.extractOne(
            normalized_input, normalized_list, scorer=fuzz.token_sort_ratio
        )

        if score >= 90:
            original_name = normalized_to_original[best_norm_match]
            print(
                f"DEBUG: Fuzzy match for '{name}': '{original_name}' (score: {score})"
            )
            return cache[original_name]

    print(f"DEBUG: No match found for '{name}'")
    return None


# Test Cases
cache = {
    "Paulo Sergio Junior": MockPerson(1, "Paulo Sergio Junior"),
    "Maria Aparecida Santos": MockPerson(2, "Maria Aparecida Santos"),
}

print("Testing Normalization:")
print(f"'Pãulo Sérgio Junior' -> '{normalize_name('Pãulo Sérgio Junior')}'")
print(f"'Maria-Aparecida Santos!' -> '{normalize_name('Maria-Aparecida Santos!')}'")

print("\nTesting Matching:")
p1 = get_person("Paulo Sergio Junior", cache)
assert p1.id == 1

p2 = get_person("Pãulo Sérgio Junior", cache)
assert p2.id == 1

p3 = get_person("Maria Aparecida-Santos", cache)
assert p3.id == 2

print("\nFuzzy Matching Score Check:")


def check_score(n1, n2):
    s1 = normalize_name(n1)
    s2 = normalize_name(n2)
    score = fuzz.token_sort_ratio(s1, s2)
    print(f"Score '{s1}' vs '{s2}': {score}")


check_score("Paulo Sergio Junior", "Paulo S Junior")
check_score("Paulo Sergio Junior", "Paulo Sergio Jr")
check_score("Paulo Sergio Junior", "Junior Paulo Sergio")
check_score("Maria Aparecida Santos", "Maria A Santos")
