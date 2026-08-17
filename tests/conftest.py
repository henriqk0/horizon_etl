import pytest


@pytest.fixture(autouse=True)
def _reset_researcher_resolution_snapshot_caches():
    """researcher_resolution.py caches candidate scoring fields keyed by
    id(researcher)/id(person) (Python object identity) to stay immune to
    SQLAlchemy session invalidation mid-run (see _get_candidate_snapshot's
    docstring). Object ids can be reused across tests once a prior test's
    mock/SimpleNamespace objects are garbage collected, so reset the caches
    around every test to keep them isolated."""
    from src.core.logic.researcher_resolution import _reset_candidate_snapshot_cache

    _reset_candidate_snapshot_cache()
    yield
    _reset_candidate_snapshot_cache()
