"""Tests for the process-isolated weekly orchestrator.

Verifies the property that motivated it: one phase crashing (segfault,
non-zero exit, or timeout) must not stop later phases, while a failure in a
critical phase must still make the whole run exit non-zero.
"""

import subprocess
from unittest.mock import MagicMock, patch

import src.flows.pipelines.weekly_orchestrator as wo


def _fake_run_factory(fail_cmd=None, rc=1, timeout_cmd=None, seen=None):
    def fake_run(argv, timeout=None):
        cmd = argv[2]
        if seen is not None:
            seen.append(cmd)
        if timeout_cmd and cmd == timeout_cmd:
            raise subprocess.TimeoutExpired(argv, timeout)
        m = MagicMock()
        m.returncode = rc if cmd == fail_cmd else 0
        return m

    return fake_run


def test_describe_rc_signal_and_exit():
    assert wo._describe_rc(139) == "killed by signal 11"
    assert wo._describe_rc(-11) == "killed by signal 11"
    assert wo._describe_rc(0) == "exit 0"
    assert wo._describe_rc(None) == "timeout"


def test_noncritical_segfault_does_not_stop_later_phases():
    seen = []
    fake = _fake_run_factory(fail_cmd="ingest_lattes_projects", rc=139, seen=seen)
    with (
        patch("src.notifications.telegram.send_telegram_message", return_value=True),
        patch.object(wo.subprocess, "run", side_effect=fake),
    ):
        rc = wo.run_weekly()
    # non-critical crash -> overall success, and everything after it still ran
    assert rc == 0
    after = seen[seen.index("ingest_lattes_projects") + 1 :]
    assert "export_canonical" in after
    assert "anonymize_backfill" in after


def test_critical_export_failure_fails_run():
    with (
        patch("src.notifications.telegram.send_telegram_message", return_value=True),
        patch.object(
            wo.subprocess,
            "run",
            side_effect=_fake_run_factory(fail_cmd="export_canonical"),
        ),
    ):
        assert wo.run_weekly() == 1


def test_all_ok_returns_zero():
    with (
        patch("src.notifications.telegram.send_telegram_message", return_value=True),
        patch.object(wo.subprocess, "run", side_effect=_fake_run_factory()),
    ):
        assert wo.run_weekly() == 0


def test_noncritical_timeout_does_not_fail_but_later_phases_still_run():
    # sigpesq is deliberately non-critical (see _PHASES in
    # weekly_orchestrator.py): the backup-merger resilience architecture
    # means a SigPesq outage/timeout should not fail the whole weekly run,
    # since merge_backup covers for the missing scraped data.
    seen = []
    with (
        patch("src.notifications.telegram.send_telegram_message", return_value=True),
        patch.object(
            wo.subprocess,
            "run",
            side_effect=_fake_run_factory(timeout_cmd="sigpesq", seen=seen),
        ),
    ):
        rc = wo.run_weekly()
    assert rc == 0
    assert "export_canonical" in seen  # isolation: sigpesq timeout didn't abort the run


def test_critical_timeout_fails_run_but_later_phases_still_run():
    seen = []
    with (
        patch("src.notifications.telegram.send_telegram_message", return_value=True),
        patch.object(
            wo.subprocess,
            "run",
            side_effect=_fake_run_factory(timeout_cmd="export_canonical", seen=seen),
        ),
    ):
        rc = wo.run_weekly()
    assert rc == 1
    # isolation: a critical phase timing out still doesn't abort later phases
    assert "anonymize_backfill" in seen


def test_telegram_failure_never_changes_outcome():
    with (
        patch(
            "src.notifications.telegram.send_telegram_message",
            side_effect=RuntimeError("boom"),
        ),
        patch.object(wo.subprocess, "run", side_effect=_fake_run_factory()),
    ):
        assert wo.run_weekly() == 0
