from typing import Any, Iterable, Optional

from loguru import logger
from sqlalchemy import text

from src.adapters.sources.lattes_parser import LattesParser
from src.core.logic.researcher_creation import (
    _ensure_researcher_row,
    create_researcher_with_resume_fallback,
)
from src.research_domain_compat import AdvisorshipRole


def resolve_researcher_from_lattes(
    all_researchers: Iterable[Any],
    *,
    lattes_id: Optional[str] = None,
    json_name: Optional[str] = None,
    session: Any = None,
) -> Optional[Any]:
    """Find the best existing Researcher for a Lattes curriculum.

    The dataset may contain duplicates that differ only by accents/casing.
    We score candidates using stable identifiers first, then normalized name,
    and finally prefer the record that already has linked data in the DB.
    """

    parser = LattesParser()
    json_name_norm = parser.normalize_title(json_name) if json_name else ""

    best = None
    best_score = float("-inf")

    for researcher in all_researchers:
        score = _score_candidate(
            researcher,
            lattes_id=lattes_id,
            json_name=json_name,
            json_name_norm=json_name_norm,
            session=session,
        )
        if score > best_score:
            best = researcher
            best_score = score

    if best_score <= 0:
        return None

    logger.debug(
        "Resolved Lattes researcher '{}' (Lattes ID: {}) to DB ID {} with score {}.",
        json_name,
        lattes_id,
        getattr(best, "id", None),
        best_score,
    )
    return best


def resolve_researcher_by_name(
    all_researchers: Iterable[Any],
    *,
    name: Optional[str],
    identification_id: Optional[str] = None,
) -> Optional[Any]:
    if not name:
        return None

    parser = LattesParser()
    target_norm = parser.normalize_title(name)

    best = None
    best_score = float("-inf")
    for researcher in all_researchers:
        score = 0
        res_name = getattr(researcher, "name", None) or ""
        res_identification = getattr(researcher, "identification_id", None) or ""

        if (
            identification_id
            and res_identification
            and str(res_identification).casefold() == str(identification_id).casefold()
        ):
            score += 200
        if res_name and res_name.casefold() == name.casefold():
            score += 150
        elif parser.normalize_title(res_name) == target_norm:
            score += 100

        if score > best_score:
            best = researcher
            best_score = score

    return best if best_score > 0 else None


def resolve_or_create_researcher(
    researcher_ctrl: Any,
    all_researchers: list[Any],
    *,
    name: Optional[str],
    identification_id: Optional[str] = None,
    emails: Optional[list[str]] = None,
    session: Any = None,
) -> Optional[Any]:
    researcher = resolve_researcher_by_name(
        all_researchers,
        name=name,
        identification_id=identification_id,
    )
    if researcher:
        return researcher

    if not name:
        return None

    # Try to find a matching Person (created by SigPesq via PersonMatcher)
    # and promote them to Researcher so we don't create a duplicate.
    person = _find_person_by_name(name, session)
    if person:
        person_id = getattr(person, "id", None)
        if person_id:
            _ensure_researcher_row(researcher_ctrl, person_id)
            try:
                promoted = researcher_ctrl.get_by_id(person_id)
                all_researchers.append(promoted)
                logger.debug(
                    f"Promoted existing Person '{name}' (id={person_id}) to Researcher."
                )
                return promoted
            except Exception:
                pass

    researcher = create_researcher_with_resume_fallback(
        researcher_ctrl,
        name=name,
        identification_id=identification_id,
        emails=emails,
    )
    if researcher:
        all_researchers.append(researcher)
    return researcher


def _find_person_by_name(name: str, session: Any) -> Optional[Any]:
    """Search the persons table for a name match.

    When multiple persons share the same name, prefers the one that is
    already promoted to a Researcher (has a row in the researchers table).
    Falls back to accent-insensitive matching (PostgreSQL unaccent) if
    exact case-insensitive match misses.
    Returns the best match or None.
    """
    if not name or not session:
        return None

    name = name.strip()
    name_lower = name.lower()

    try:
        rows = session.execute(
            text(
                """
                SELECT id, name FROM persons
                WHERE lower(name) = :name_lower
                """
            ),
            {"name_lower": name_lower},
        ).fetchall()

        if not rows:
            # Fallback: accent-insensitive match (PostgreSQL unaccent extension)
            try:
                rows = session.execute(
                    text(
                        """
                        SELECT id, name FROM persons
                        WHERE unaccent(lower(name)) = unaccent(:name_lower)
                        """
                    ),
                    {"name_lower": name_lower},
                ).fetchall()
            except Exception:
                pass

        if rows:
            # Prefer a person that is already a researcher (already promoted)
            for row in rows:
                is_res = session.execute(
                    text("SELECT 1 FROM researchers WHERE id = :pid"),
                    {"pid": row[0]},
                ).scalar()
                if is_res:

                    class _Match:
                        pass

                    m = _Match()
                    m.id, m.name = row[0], row[1]
                    return m

            # Otherwise, return the first match
            class _Match:
                pass

            m = _Match()
            m.id, m.name = rows[0][0], rows[0][1]
            return m

    except Exception:
        pass

    return None


def _score_candidate(
    researcher: Any,
    *,
    lattes_id: Optional[str],
    json_name: Optional[str],
    json_name_norm: str,
    session: Any,
) -> int:
    parser = LattesParser()

    score = 0
    matched = False
    name = getattr(researcher, "name", None) or ""
    identification_id = getattr(researcher, "identification_id", None) or ""
    brand_id = getattr(researcher, "brand_id", None) or ""
    cnpq_url = getattr(researcher, "cnpq_url", None) or ""

    if lattes_id:
        if str(brand_id) == lattes_id:
            score += 500
            matched = True
        if str(identification_id) == lattes_id:
            score += 400
            matched = True
        if lattes_id in str(cnpq_url):
            score += 350
            matched = True

    if json_name:
        if name.casefold() == json_name.casefold():
            score += 200
            matched = True
        elif parser.normalize_title(name) == json_name_norm:
            score += 150
            matched = True

    if not matched:
        return 0

    score += _linked_data_score(getattr(researcher, "id", None), session)

    if getattr(researcher, "resume", None):
        score += 25
    if getattr(researcher, "citation_names", None):
        score += 10

    return score


def _linked_data_score(person_id: Optional[int], session: Any) -> int:
    if not person_id or session is None:
        return 0

    try:
        row = session.execute(
            text(
                """
                SELECT
                    (
                        SELECT COUNT(*)
                        FROM advisorship_members
                        WHERE role_name = :supervisor_role
                          AND person_id = :pid
                    ) +
                    (SELECT COUNT(*) FROM academic_educations WHERE researcher_id = :pid) +
                    (SELECT COUNT(*) FROM article_authors WHERE researcher_id = :pid)
                """
            ),
            {
                "pid": person_id,
                "supervisor_role": AdvisorshipRole.SUPERVISOR.value,
            },
        ).fetchone()
        return int(row[0] or 0) * 20 if row else 0
    except Exception:
        try:
            row = session.execute(
                text(
                    """
                    SELECT
                        (
                            SELECT COUNT(*)
                            FROM advisorships
                            WHERE supervisor_id = :pid
                        ) +
                        (SELECT COUNT(*) FROM academic_educations WHERE researcher_id = :pid) +
                        (SELECT COUNT(*) FROM article_authors WHERE researcher_id = :pid)
                    """
                ),
                {"pid": person_id},
            ).fetchone()
            return int(row[0] or 0) * 20 if row else 0
        except Exception:
            return 0
