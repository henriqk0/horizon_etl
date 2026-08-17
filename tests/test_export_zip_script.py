"""Exit-code contract of scripts/export_zip.py.

Regression guard: the script used to `sys.exit(0)` whenever no archive came
back, which conflated two very different outcomes. A validation failure
deletes the archive it just built, so reporting success there made the weekly
orchestrator print `export_zip ✓` for a run that had left no export behind at
all — and, with the LIVE-only backup rule, would have let such a run refresh
the reference backup.
"""

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "export_zip.py"


def _run(output_dir: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(output_dir)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )


def _write_contract_files(target: Path) -> None:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from export_zip import EXPECTED_TOP_LEVEL

    for name in EXPECTED_TOP_LEVEL:
        (target / name).write_text(json.dumps([]), encoding="utf-8")


def test_validation_failure_exits_non_zero(tmp_path: Path) -> None:
    _write_contract_files(tmp_path)
    (tmp_path / "unexpected_extra.json").write_text("[]", encoding="utf-8")

    result = _run(tmp_path)

    assert result.returncode != 0, (
        "Validation failure must exit non-zero so the orchestrator marks the "
        f"phase failed. stdout:\n{result.stdout}"
    )
    assert not (tmp_path / "export.zip").exists()


def test_complete_export_exits_zero(tmp_path: Path) -> None:
    _write_contract_files(tmp_path)

    result = _run(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "export.zip").exists()


def test_nothing_to_zip_is_not_a_failure(tmp_path: Path) -> None:
    """An empty directory is a no-op, not an error — re-running after
    --clean-loose already removed the loose JSONs must stay exit 0."""
    result = _run(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
