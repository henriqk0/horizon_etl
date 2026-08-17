from unittest.mock import MagicMock

from src.core.logic.team_synchronizer import TeamSynchronizer


class MockTeam:
    def __init__(self, team_id, name):
        self.id = team_id
        self.name = name


def test_ensure_team_matches_canonical_name():
    team_controller = MagicMock()
    team_controller.get_all.return_value = [MockTeam(1, "Conecta FAPES")]
    synchronizer = TeamSynchronizer(team_controller, roles_cache={})

    team = synchronizer.ensure_team("Conecta Fapes", "desc")

    assert team.id == 1
    team_controller.create_team.assert_not_called()


def test_ensure_team_uses_index_instead_of_linear_scan(monkeypatch):
    """Perf regression guard: this was the actual root cause of the
    lattes_advisorships timeout — ensure_team() used to re-normalize every
    cached team's name (Unicode NFD + genexpr) on every single call, doing
    a full linear scan of the whole (growing, thousands-of-rows) teams
    table each time. Confirmed via cProfile against real data: ~1.5M
    normalize_text calls for just 15 files. Assert normalize_text is only
    called a small, bounded number of times per lookup, not once per
    cached team."""
    import src.core.logic.team_synchronizer as team_synchronizer_module

    team_controller = MagicMock()
    team_controller.get_all.return_value = [
        MockTeam(i, f"Team {i}") for i in range(5000)
    ]
    synchronizer = TeamSynchronizer(team_controller, roles_cache={})

    # First call triggers the one-time cache/index build (normalizes every
    # cached team's name exactly once) — that part is expected and fine.
    synchronizer.ensure_team("Team 0", "desc")

    calls = {"n": 0}
    orig = team_synchronizer_module.normalize_text

    def counting_normalize(*a, **kw):
        calls["n"] += 1
        return orig(*a, **kw)

    monkeypatch.setattr(team_synchronizer_module, "normalize_text", counting_normalize)

    # A second, later lookup against the already-built index must be O(1) —
    # not another full scan re-normalizing all 5000 cached teams.
    team = synchronizer.ensure_team("Team 4999", "desc")

    assert team.id == 4999
    assert calls["n"] < 10


def test_ensure_team_index_persists_across_calls():
    team_controller = MagicMock()
    team_controller.get_all.return_value = [MockTeam(1, "Existing Team")]
    synchronizer = TeamSynchronizer(team_controller, roles_cache={})
    team_controller.create_team.return_value = MockTeam(2, "New Team")

    synchronizer.ensure_team("New Team", "desc")
    team_controller.get_all.assert_called_once()

    # A second call for the newly created team must hit the index, not
    # trigger another get_all() or a fresh linear scan.
    found = synchronizer.ensure_team("New Team", "desc")
    assert found.id == 2
    team_controller.get_all.assert_called_once()
    team_controller.create_team.assert_called_once()
