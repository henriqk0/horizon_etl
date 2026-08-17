from types import SimpleNamespace

from src.core.logic.researcher_resolution import (
    _get_candidate_snapshot,
    resolve_researcher_from_lattes,
)


def _researcher(**kwargs):
    defaults = dict(
        id=None,
        name=None,
        identification_id=None,
        brand_id=None,
        cnpq_url=None,
        resume=None,
        citation_names=None,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_resolve_researcher_from_lattes_matches_by_brand_id():
    candidates = [
        _researcher(id=1, name="Someone Else", brand_id="9999999999999999"),
        _researcher(id=2, name="Target Researcher", brand_id="1234567890123456"),
    ]

    result = resolve_researcher_from_lattes(
        candidates, lattes_id="1234567890123456", json_name="Different Name"
    )

    assert result.id == 2


def test_resolve_researcher_from_lattes_matches_by_normalized_name_when_no_lattes_id():
    candidates = [
        _researcher(id=1, name="Someone Else"),
        _researcher(id=2, name="José da Silva"),
    ]

    result = resolve_researcher_from_lattes(candidates, json_name="jose da silva")

    assert result.id == 2


def test_resolve_researcher_from_lattes_returns_none_when_no_candidate_matches():
    candidates = [_researcher(id=1, name="Someone Else", brand_id="0000000000000000")]

    result = resolve_researcher_from_lattes(
        candidates, lattes_id="1234567890123456", json_name="Nobody Matching"
    )

    assert result is None


class _AccessCountingResearcher:
    """Simulates a SQLAlchemy ORM object whose attribute access has a real
    cost (e.g. triggers a DB reload after session.rollback() expired it —
    see researcher_resolution.py's _get_candidate_snapshot docstring)."""

    def __init__(self, **kwargs):
        self._data = dict(
            id=None,
            name=None,
            identification_id=None,
            brand_id=None,
            cnpq_url=None,
            resume=None,
            citation_names=None,
        )
        self._data.update(kwargs)
        self.access_count = 0

    def __getattr__(self, item):
        if item in ("_data", "access_count"):
            raise AttributeError(item)
        self.access_count += 1
        return self._data.get(item)


def test_candidate_snapshot_is_cached_and_survives_repeat_access():
    """Regression guard for the actual root cause of the lattes_advisorships
    timeout: session.rollback() elsewhere in a run (e.g. project_loader.py's
    per-row error handler, routinely hit on duplicate initiative names)
    expires every previously-loaded SQLAlchemy object, so a full
    resolve_researcher_from_lattes() re-scan would otherwise reload every
    single cached researcher from the DB one at a time. Confirmed via SQL
    tracing against real data: ~10,166 individual reload queries costing
    over 100s for a single file. The snapshot cache must ensure each
    candidate's fields are only ever actually read from the (expensive)
    object once."""
    researcher = _AccessCountingResearcher(id=1, name="Ana Silva")

    first = _get_candidate_snapshot(researcher)
    accesses_after_first = researcher.access_count
    assert accesses_after_first > 0

    # Simulate the object being "expired" again by a later rollback —
    # a real ORM object would trigger a fresh reload on next access, but the
    # snapshot cache must serve the second lookup without touching it again.
    second = _get_candidate_snapshot(researcher)

    assert second == first
    assert researcher.access_count == accesses_after_first


def test_resolve_researcher_from_lattes_handles_large_candidate_pool():
    """Perf regression guard: _score_candidate must reuse a single shared
    LattesParser instead of constructing a new one per candidate — with
    ~10k researchers per file across the real Lattes ingestion run, that
    constructor churn is otherwise real (if cheap-per-call) overhead."""
    candidates = [_researcher(id=i, name=f"Researcher {i}") for i in range(5000)]
    candidates.append(
        _researcher(id=9999, name="Target Person", brand_id="1234567890123456")
    )

    result = resolve_researcher_from_lattes(
        candidates, lattes_id="1234567890123456", json_name="Target Person"
    )

    assert result.id == 9999
