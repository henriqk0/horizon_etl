from unittest.mock import MagicMock

from research_domain.domain.entities import Advisorship

from src.core.logic.project_loader import ProjectLoader


def _make_loader_for_process_records():
    loader = ProjectLoader.__new__(ProjectLoader)
    loader.controller = MagicMock()
    loader.controller.get_all.return_value = []
    loader.person_matcher = MagicMock()
    loader.person_matcher._persons_cache = {}
    loader._initiatives_cache = None
    return loader


def test_process_records_builds_existing_dicts_once_across_calls():
    """Perf/correctness regression guard: existing_by_name/existing_by_identity
    used to be rebuilt from scratch (re-scanning every cached initiative) on
    every single process_records() call — this loader runs once per source
    file, so that was O(files * initiatives) of wasted work. They must now
    be built once, alongside _initiatives_cache, and reused/mutated across
    calls."""
    loader = _make_loader_for_process_records()

    loader.process_records([])
    first_by_name = loader._existing_by_name
    first_by_identity = loader._existing_by_identity

    loader.process_records([])

    # get_all() (the expensive DB fetch) must only run once across both calls.
    loader.controller.get_all.assert_called_once()
    # The exact same dict objects are reused (not rebuilt) across calls, so
    # any initiative registered mid-run stays visible to later files.
    assert loader._existing_by_name is first_by_name
    assert loader._existing_by_identity is first_by_identity


def test_process_records_keeps_mid_run_initiative_visible_across_calls():
    loader = _make_loader_for_process_records()

    loader.process_records([])
    new_initiative = MagicMock()
    loader._existing_by_name["A New Project"] = new_initiative

    loader.process_records([])

    assert loader._existing_by_name["A New Project"] is new_initiative


def test_is_advisorship_candidate_caches_db_lookup_by_id():
    """Perf regression guard: this was a real contributor to the
    lattes_advisorships timeout — _is_advisorship_candidate's fallback path
    hit adv_controller.get_by_id() (a DB round trip) every single time a
    non-Advisorship-typed cached candidate was checked, up to twice per row
    via _resolve_existing_initiative. Confirmed via SQL tracing against
    real data: hundreds of redundant queries per file. The polymorphic fact
    for a given initiative id never changes mid-run, so it must be cached."""
    loader = ProjectLoader.__new__(ProjectLoader)
    loader.adv_controller = MagicMock()
    found_advisorship = MagicMock(spec=Advisorship)
    loader.adv_controller.get_by_id.return_value = found_advisorship

    candidate = MagicMock()
    candidate.id = 42

    first = loader._is_advisorship_candidate(candidate)
    second = loader._is_advisorship_candidate(candidate)

    assert first is True
    assert second is True
    loader.adv_controller.get_by_id.assert_called_once_with(42)


def test_resolve_existing_initiative_prefers_same_model_when_identity_hits_wrong_type():
    loader = ProjectLoader.__new__(ProjectLoader)
    loader.adv_controller = MagicMock()
    loader.controller = MagicMock()

    research_project = MagicMock()
    research_project.id = 1338

    advisorship = MagicMock(spec=Advisorship)
    advisorship.id = 113

    loader.adv_controller.get_by_id.side_effect = [
        None,
        advisorship,
    ]

    existing = loader._resolve_existing_initiative(
        existing_by_name={
            "Instrumentação de um robô móvel para serviços de vigilância.": advisorship
        },
        existing_by_identity={
            "instrumentacao de um robo movel para servicos de vigilancia": research_project
        },
        model_class=Advisorship,
        identity_key="instrumentacao de um robo movel para servicos de vigilancia",
        title="Instrumentação de um robô móvel para serviços de vigilância.",
    )

    assert existing is advisorship


def test_register_existing_initiative_keeps_parent_mapping_when_child_shares_title():
    loader = ProjectLoader.__new__(ProjectLoader)
    loader.adv_controller = MagicMock()
    loader.adv_controller.get_by_id.return_value = None

    parent_project = MagicMock()
    parent_project.id = 258

    child_advisorship = MagicMock(spec=Advisorship)
    child_advisorship.id = 999

    existing_by_name = {
        "Desenvolvimento de uma plataforma de aquisição de sinais cerebrais para projetos orientados a robótica": parent_project
    }

    loader._register_existing_initiative(
        existing_by_name=existing_by_name,
        title="Desenvolvimento de uma plataforma de aquisição de sinais cerebrais para projetos orientados a robótica",
        initiative=child_advisorship,
        model_class=Advisorship,
    )

    assert (
        existing_by_name[
            "Desenvolvimento de uma plataforma de aquisição de sinais cerebrais para projetos orientados a robótica"
        ]
        is parent_project
    )
