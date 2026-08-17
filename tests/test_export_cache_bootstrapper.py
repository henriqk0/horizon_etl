import zipfile

from src.core.logic.export_cache_bootstrapper import ExportCacheBootstrapper


def test_bootstrap_extracts_files_into_target_dir(tmp_path):
    exports_dir = tmp_path / "data" / "exports"
    exports_dir.mkdir(parents=True)
    archive_path = exports_dir / "export.zip"
    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr("researchers_canonical.json", "[]")
        zf.writestr("nested/dir/file.json", "{}")

    target_dir = tmp_path / "restored"
    result = ExportCacheBootstrapper().bootstrap(
        target_dir=str(target_dir), search_dirs=[str(exports_dir)]
    )

    assert result["restored"] is True
    assert result["files_extracted"] == 2
    assert (target_dir / "researchers_canonical.json").is_file()
    assert (target_dir / "nested" / "dir" / "file.json").is_file()


def test_bootstrap_rejects_zip_slip_path_traversal(tmp_path):
    """Security regression guard (CWE-22 / "Zip Slip"): a zip member whose
    name escapes the target directory via ../ must never be extracted
    outside it, even if the archive is otherwise well-formed."""
    exports_dir = tmp_path / "data" / "exports"
    exports_dir.mkdir(parents=True)
    archive_path = exports_dir / "export.zip"
    escape_target = tmp_path / "outside_evil.txt"

    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr("safe_file.json", "{}")
        zf.writestr("../outside_evil.txt", "pwned")

    target_dir = tmp_path / "restored"
    result = ExportCacheBootstrapper().bootstrap(
        target_dir=str(target_dir), search_dirs=[str(exports_dir)]
    )

    assert result["restored"] is False
    assert not escape_target.exists()
    # Nothing from the malicious archive should have been extracted, including
    # the otherwise-safe member, since the whole extraction is rejected.
    assert not (target_dir / "safe_file.json").exists()


def test_bootstrap_rejects_absolute_path_member(tmp_path):
    exports_dir = tmp_path / "data" / "exports"
    exports_dir.mkdir(parents=True)
    archive_path = exports_dir / "export.zip"
    escape_target = tmp_path / "abs_evil.txt"

    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr(str(escape_target), "pwned")

    target_dir = tmp_path / "restored"
    result = ExportCacheBootstrapper().bootstrap(
        target_dir=str(target_dir), search_dirs=[str(exports_dir)]
    )

    assert result["restored"] is False
    assert not escape_target.exists()
