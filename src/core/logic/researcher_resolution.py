from typing import Any, Dict, Iterable, Optional, Tuple

from loguru import logger
from sqlalchemy import text

from src.adapters.sources.lattes_parser import LattesParser
from src.core.logic.researcher_creation import (
    _ensure_researcher_row,
    create_researcher_with_resume_fallback,
)
from src.research_domain_compat import AdvisorshipRole

# Snapshot of the scoring-relevant fields for a candidate
# (name, identification_id, brand_id, cnpq_url, id, resume, citation_names),
# keyed by id(researcher) (Python object identity — cheap, never touches the
# DB). See _get_candidate_snapshot for why this cache exists.
_candidate_snapshot_cache: Dict[int, Tuple[str, str, str, str, Any, str, str]] = {}


# Lighter-weight (name, identification_id) snapshot cache shared by
# resolve_researcher_by_name/resolve_person_by_name — same rollback-reload
# vulnerability as _candidate_snapshot_cache, smaller payload since neither
# function needs brand_id/cnpq_url/resume/citation_names.
_name_snapshot_cache: Dict[int, Tuple[str, str]] = {}


def _reset_candidate_snapshot_cache() -> None:
    """Test/process-boundary hook — clears the module-level snapshot caches."""
    _candidate_snapshot_cache.clear()
    _name_snapshot_cache.clear()


def _get_name_snapshot(entity: Any) -> Tuple[str, str]:
    """Returns (name, identification_id) for a Researcher/Person candidate,
    extracted once and cached by object identity — see
    _get_candidate_snapshot's docstring for why this exists."""
    key = id(entity)
    cached = _name_snapshot_cache.get(key)
    if cached is not None:
        return cached
    snapshot = (
        getattr(entity, "name", None) or "",
        getattr(entity, "identification_id", None) or "",
    )
    _name_snapshot_cache[key] = snapshot
    return snapshot


def _get_candidate_snapshot(
    researcher: Any,
) -> Tuple[str, str, str, str, Any, str, str]:
    """Returns (name, identification_id, brand_id, cnpq_url, id, resume,
    citation_names) for a candidate, extracted once and cached by object
    identity.

    Without this, _score_candidate's attribute access went straight to the
    live SQLAlchemy object. That's normally cheap, but any session.rollback()
    elsewhere in the run (e.g. project_loader.py's per-row error handler,
    hit routinely on duplicate initiative names) expires every object
    already loaded into that session — including all ~10k cached
    researchers. The next full resolve_researcher_from_lattes() scan then
    reloads each one individually from the DB (confirmed via SQL tracing:
    ~10,166 individual "SELECT researchers JOIN persons ..." queries costing
    over 100s for a single Lattes file). Caching the handful of plain fields
    actually needed for scoring makes the scan immune to that invalidation
    after the first successful read of each candidate.
    """
    key = id(researcher)
    cached = _candidate_snapshot_cache.get(key)
    if cached is not None:
        return cached
    snapshot = (
        getattr(researcher, "name", None) or "",
        getattr(researcher, "identification_id", None) or "",
        getattr(researcher, "brand_id", None) or "",
        getattr(researcher, "cnpq_url", None) or "",
        getattr(researcher, "id", None),
        getattr(researcher, "resume", None) or "",
        getattr(researcher, "citation_names", None) or "",
    )
    _candidate_snapshot_cache[key] = snapshot
    return snapshot


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
            parser=parser,
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
        res_name, res_identification = _get_name_snapshot(researcher)

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


def resolve_person_by_name(
    all_persons: Iterable[Any],
    *,
    name: Optional[str],
    identification_id: Optional[str] = None,
) -> Optional[Any]:
    """Find a person among ALL persons (including persons-only rows).

    The `researchers` table only holds joined-table rows for people that became
    researchers. SigPesq-created students live solely in `persons`; matching them
    here prevents CNPq/Lattes syncs from minting duplicate researchers.
    """
    if not name:
        return None

    parser = LattesParser()
    target_norm = parser.normalize_title(name)

    best = None
    best_score = float("-inf")
    for person in all_persons:
        score = 0
        p_name, p_identification = _get_name_snapshot(person)

        if (
            identification_id
            and p_identification
            and str(p_identification).casefold() == str(identification_id).casefold()
        ):
            score += 200
        if p_name and p_name.casefold() == name.casefold():
            score += 150
        elif parser.normalize_title(p_name) == target_norm:
            score += 100

        if score > best_score:
            best = person
            best_score = score

    return best if best_score > 0 else None


def resolve_or_create_researcher(
    researcher_ctrl: Any,
    all_researchers: list[Any],
    *,
    name: Optional[str],
    identification_id: Optional[str] = None,
    emails: Optional[list[str]] = None,
    all_persons: Optional[Iterable[Any]] = None,
    session: Any = None,
) -> Optional[Any]:
    researcher = resolve_researcher_by_name(
        all_researchers,
        name=name,
        identification_id=identification_id,
    )
    if researcher:
        return researcher

    # Fall back to persons-only rows (e.g. SigPesq students that never became
    # researchers). Reusing the existing person consolidates rather than
    # duplicating; the caller's self-healing backfills the 'researchers' row.
    if all_persons:
        person = resolve_person_by_name(
            all_persons,
            name=name,
            identification_id=identification_id,
        )
        if person:
            return person

    if not name:
        return None

    # Try to find a matching Person (created by SigPesq via PersonMatcher)
    # and promote them to Researcher so we don't create a duplicate.
    if session is None:
        try:
            session = researcher_ctrl._service._repository._session
        except Exception:
            pass
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
            text("""
                SELECT id, name FROM persons
                WHERE lower(name) = :name_lower
                """),
            {"name_lower": name_lower},
        ).fetchall()

        if not rows:
            # Fallback: accent-insensitive match (PostgreSQL unaccent extension)
            try:
                rows = session.execute(
                    text("""
                        SELECT id, name FROM persons
                        WHERE unaccent(lower(name)) = unaccent(:name_lower)
                        """),
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
    parser: LattesParser,
) -> int:
    score = 0
    matched = False
    (
        name,
        identification_id,
        brand_id,
        cnpq_url,
        researcher_id,
        resume,
        citation_names,
    ) = _get_candidate_snapshot(researcher)

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

    score += _linked_data_score(researcher_id, session)

    if resume:
        score += 25
    if citation_names:
        score += 10

    return score


def _linked_data_score(person_id: Optional[int], session: Any) -> int:
    if not person_id or session is None:
        return 0

    try:
        row = session.execute(
            text("""
                SELECT
                    (
                        SELECT COUNT(*)
                        FROM advisorship_members
                        WHERE role_name = :supervisor_role
                          AND person_id = :pid
                    ) +
                    (SELECT COUNT(*) FROM academic_educations WHERE researcher_id = :pid) +
                    (SELECT COUNT(*) FROM article_authors WHERE researcher_id = :pid)
                """),
            {
                "pid": person_id,
                "supervisor_role": AdvisorshipRole.SUPERVISOR.value,
            },
        ).fetchone()
        return int(row[0] or 0) * 20 if row else 0
    except Exception:
        try:
            row = session.execute(
                text("""
                    SELECT
                        (
                            SELECT COUNT(*)
                            FROM advisorships
                            WHERE supervisor_id = :pid
                        ) +
                        (SELECT COUNT(*) FROM academic_educations WHERE researcher_id = :pid) +
                        (SELECT COUNT(*) FROM article_authors WHERE researcher_id = :pid)
                    """),
                {"pid": person_id},
            ).fetchone()
            return int(row[0] or 0) * 20 if row else 0
        except Exception:
            return 0
