import re
import unicodedata
from typing import Dict, List, Optional

from eo_lib import Person, PersonController
from loguru import logger
from thefuzz import fuzz, process

from src.core.logic.pii_anonymizer import anonymize_email, is_anonymized_email


class PersonMatcher:
    """
    Service responsible for matching incoming names with existing Person records.

    This class handles name normalization, fuzzy matching, and caching to ensure
    idempotency and efficiency when identifying or creating persons during ingestion.
    """

    def __init__(self, person_controller: PersonController):
        """
        Initializes the PersonMatcher.

        Args:
            person_controller (PersonController): Controller used to interact with Person records.
        """
        self.person_controller = person_controller
        self._persons_cache: Dict[str, Person] = {}
        self._emails_cache: Dict[str, Person] = {}
        self._canonical_cache: Dict[str, Person] = {}
        # Maps normalize_name(name) -> Person, maintained incrementally so
        # exact normalized-name lookups and the fuzzy-match candidate list
        # are O(1)/pre-computed instead of re-normalizing every cached name
        # on every single match_or_create() call (see normalize_name cost
        # analysis in the class docstring below).
        self._normalized_cache: Dict[str, Person] = {}

    def preload_cache(self):
        """
        Preloads the internal persons cache from the database.

        Fetches all persons and populates _persons_cache using their names
        and _emails_cache using their emails. Skips if the cache is already
        populated (new persons created mid-run are added incrementally).
        """
        if self._persons_cache:
            logger.info(
                f"Persons cache already loaded ({len(self._persons_cache)} persons, "
                f"{len(self._emails_cache)} emails). Skipping reload."
            )
            return
        logger.info("Pre-loading persons cache...")
        try:
            all_persons = self.person_controller.get_all()
            self._persons_cache = {}
            self._emails_cache = {}
            self._canonical_cache = {}
            self._normalized_cache = {}
            for p in all_persons:
                if isinstance(p, dict):
                    name = p.get("name")
                    emails = p.get("emails") or ([p["email"]] if p.get("email") else [])
                else:
                    name = getattr(p, "name", None)
                    # Person has an `emails` relationship (PersonEmail rows), not an `email` column.
                    emails = [
                        e.email if hasattr(e, "email") else e
                        for e in (getattr(p, "emails", None) or [])
                    ]
                if name:
                    self._persons_cache[name] = p
                    canonical_name = self.canonicalize_name(name)
                    if canonical_name:
                        current = self._canonical_cache.get(canonical_name)
                        if current is None or self._person_quality_score(
                            p
                        ) > self._person_quality_score(current):
                            self._canonical_cache[canonical_name] = p
                    normalized_name = self.normalize_name(name)
                    if normalized_name:
                        current = self._normalized_cache.get(normalized_name)
                        if current is None or self._person_quality_score(
                            p
                        ) > self._person_quality_score(current):
                            self._normalized_cache[normalized_name] = p
                for email in emails:
                    if email:
                        self._emails_cache[email.strip().lower()] = p
            logger.info(
                f"Loaded {len(self._persons_cache)} persons and {len(self._emails_cache)} emails into cache"
            )
        except Exception as e:
            logger.warning(f"Failed to preload persons cache: {e}")

    def normalize_name(self, name: str) -> str:
        """
        Normalizes a name for consistent comparison.

        Steps:
        1. Normalize Unicode (NFD) and remove accents.
        2. Replace special characters with spaces and convert to UPPERCASE.
        3. Trim and remove double spaces.

        Args:
            name (str): The raw name string to normalize.

        Returns:
            str: The normalized name string.
        """
        if not name:
            return ""
        # 1. Normalize Unicode (NFD) and remove accents
        name_str = "".join(
            c
            for c in unicodedata.normalize("NFD", name)
            if unicodedata.category(c) != "Mn"
        )

        # 2. Replace special characters with spaces and Uppercase
        name_str = re.sub(r"[^A-Z\s]", " ", name_str.upper())

        # 3. Trim and remove double spaces
        return " ".join(name_str.split())

    def canonicalize_name(self, name: str) -> str:
        """Builds a stable comparison key for names."""
        normalized = self.normalize_name(name)
        if not normalized:
            return ""

        # Particles are preserved but normalized to a single representation
        particles = {"DA", "DE", "DI", "DO", "DOS", "DAS", "DU", "DEL", "DELA"}
        tokens = [
            token if token not in particles else token.lower()
            for token in normalized.split()
        ]
        return " ".join(tokens)

    def _email_keys(self, email: str) -> List[str]:
        """Candidate cache keys for an email.

        Stored emails are LGPD-anonymized by the session hook, so an incoming
        raw email must also be looked up by its anonymized forms (hashed
        as-written and lowercased, since the hook does not normalize case).
        """
        stripped = email.strip()
        keys = [stripped.lower()]
        if not is_anonymized_email(stripped):
            for candidate in (
                anonymize_email(stripped),
                anonymize_email(stripped.lower()),
            ):
                if candidate and candidate not in keys:
                    keys.append(candidate)
        return keys

    def _register_email(self, email: Optional[str], person: Person) -> None:
        if not email:
            return
        for key in self._email_keys(email):
            self._emails_cache[key] = person

    def _person_quality_score(self, person: Person) -> int:
        """Prefers the richer record when duplicates share the same canonical name."""
        score = 0
        for attr in (
            "identification_id",
            "emails",
            "resume",
            "citation_names",
            "cnpq_url",
        ):
            value = (
                person.get(attr)
                if isinstance(person, dict)
                else getattr(person, attr, None)
            )
            if value:
                score += 10
        return score

    def match_or_create(
        self, name: str, email: Optional[str] = None, strict_match: bool = False
    ) -> Optional[Person]:
        """
        Finds a person by email or name.
        Uses normalization and (optionally) fuzzy matching for names.
        Creates a new Person if no match is found.

        Args:
            name (str): The name of the person to match or create.
            email (Optional[str]): The email of the person to match.
            strict_match (bool): If True, only exact normalized matches (score 100) are accepted for name.

        Returns:
            Optional[Person]: The matched or newly created Person object, or None if creation fails.
        """
        if not name or not name.strip():
            # If name is missing but email is provided, maybe we can find by email anyway?
            # User requirement says Student and Supervisor are people and we should use name OR email.
            if not email:
                return None

        # 1. Match by Email first (highest priority)
        if email:
            for email_key in self._email_keys(email):
                if email_key in self._emails_cache:
                    logger.debug(f"Match found by email: {email_key}")
                    return self._emails_cache[email_key]

        name = name.strip() if name else ""
        normalized_input = self.normalize_name(name)
        canonical_input = self.canonicalize_name(name)

        # 1.5 Canonical exact match.
        # This collapses duplicates such as "De"/"de" and accent-only variants.
        if canonical_input and canonical_input in self._canonical_cache:
            person = self._canonical_cache[canonical_input]
            self._register_email(email, person)
            self._persons_cache[name] = person
            if normalized_input:
                self._normalized_cache.setdefault(normalized_input, person)
            return person

        # 1.6 Exact raw-name match.
        if name in self._persons_cache:
            person = self._persons_cache[name]
            self._register_email(email, person)
            return person

        # 2. Exact Match in Cache (Normalized) — O(1) via the incrementally
        # maintained _normalized_cache index. This used to re-normalize
        # every cached name (an expensive Unicode NFD + regex pass) on every
        # single call, which dominated runtime once the persons cache grew
        # into the tens of thousands (see resolve_or_create_researcher /
        # ingest_lattes_advisorships_flow — this is invoked per advisorship
        # per file, so an O(n) scan here is O(files * advisorships * n)).
        if normalized_input and normalized_input in self._normalized_cache:
            person = self._normalized_cache[normalized_input]
            self._persons_cache[name] = person
            self._register_email(email, person)
            return person

        # 3. Fuzzy Matching in Cache — reuses the same pre-normalized index
        # instead of rebuilding it (re-normalizing every cached name) on
        # every call. The fuzzy scan itself (thefuzz.process.extractOne)
        # remains O(n) by nature of fuzzy matching, but the redundant
        # normalization work is eliminated.
        if self._normalized_cache and normalized_input:
            normalized_list = list(self._normalized_cache.keys())

            best_norm_match, score = process.extractOne(
                normalized_input, normalized_list, scorer=fuzz.token_sort_ratio
            )

            # Threshold of 90%
            if score >= 90:
                # If strict match is enabled, we only accept 100% score (same tokens)
                if strict_match and score < 100:
                    logger.debug(
                        f"Fuzzy match '{best_norm_match}' ignored due to strict matching policy (score: {score})"
                    )
                else:
                    person = self._normalized_cache[best_norm_match]
                    logger.info(
                        f"Fuzzy match found: '{name}' matches normalized '{best_norm_match}' (score: {score})"
                    )
                    self._persons_cache[name] = person
                    # Cache this variant so identical repeats of the same
                    # misspelling/variant hit the O(1) path (step 2) next time
                    # instead of re-running fuzzy matching.
                    self._normalized_cache.setdefault(normalized_input, person)
                    self._register_email(email, person)
                    return person

        # 4. Create new person (if no match found)
        try:
            emails = [email] if email else []
            person = self.person_controller.create_person(name=name, emails=emails)
            self._persons_cache[name] = person
            if canonical_input:
                current = self._canonical_cache.get(canonical_input)
                if current is None or self._person_quality_score(
                    person
                ) > self._person_quality_score(current):
                    self._canonical_cache[canonical_input] = person
            if normalized_input:
                current = self._normalized_cache.get(normalized_input)
                if current is None or self._person_quality_score(
                    person
                ) > self._person_quality_score(current):
                    self._normalized_cache[normalized_input] = person
            self._register_email(email, person)
            logger.debug(f"Created person: {name} (emails: {emails})")
            return person
        except Exception as e:
            logger.warning(f"Failed to create person '{name}': {e}")
            return None
