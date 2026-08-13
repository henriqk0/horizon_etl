import os
import shutil
import tempfile
from zipfile import ZipFile

import pytest

from src.core.logic.export_cache_bootstrapper import ExportCacheBootstrapper


@pytest.fixture
def temp_workspace():
    dirpath = tempfile.mkdtemp()
    exports_dir = os.path.join(dirpath, "data", "exports")
    os.makedirs(exports_dir, exist_ok=True)

    yield {"root": dirpath, "exports": exports_dir}

    shutil.rmtree(dirpath, ignore_errors=True)


def test_find_latest_archive_prefers_exports_dir(temp_workspace):
    exports_dir = temp_workspace["exports"]
    root_dir = temp_workspace["root"]

    zip_exports = os.path.join(exports_dir, "canonical_export_20260811_150000.zip")
    with ZipFile(zip_exports, "w") as zf:
        zf.writestr("test.json", "{}")

    zip_root = os.path.join(root_dir, "canonical_export_20260811_160000.zip")
    with ZipFile(zip_root, "w") as zf:
        zf.writestr("test.json", "{}")

    bootstrapper = ExportCacheBootstrapper()
    found = bootstrapper.find_latest_archive(search_dirs=[exports_dir, root_dir])

    assert found is not None
    assert str(found) == zip_exports


def test_find_latest_archive_falls_back_to_root(temp_workspace):
    exports_dir = temp_workspace["exports"]
    root_dir = temp_workspace["root"]

    zip_root = os.path.join(root_dir, "canonical_export_20260811_160000.zip")
    with ZipFile(zip_root, "w") as zf:
        zf.writestr("test.json", "{}")

    bootstrapper = ExportCacheBootstrapper()
    found = bootstrapper.find_latest_archive(search_dirs=[exports_dir, root_dir])

    assert found is not None
    assert str(found) == zip_root


def test_bootstrap_extracts_and_retains_zip(temp_workspace):
    exports_dir = temp_workspace["exports"]

    zip_path = os.path.join(exports_dir, "canonical_export_20260811_150631.zip")
    with ZipFile(zip_path, "w") as zf:
        zf.writestr("project_sigpesq_files_json/PJ_100.json", '{"id": 100}')
        zf.writestr("initiatives_canonical.json", "[]")

    bootstrapper = ExportCacheBootstrapper()
    result = bootstrapper.bootstrap(target_dir=exports_dir, search_dirs=[exports_dir])

    assert result["restored"] is True
    assert result["archive_used"] == zip_path
    assert result["files_extracted"] == 2
    assert os.path.exists(zip_path)

    extracted_pj = os.path.join(
        exports_dir, "project_sigpesq_files_json", "PJ_100.json"
    )
    assert os.path.exists(extracted_pj)


def test_bootstrap_graceful_fallback_when_no_zip(temp_workspace):
    exports_dir = temp_workspace["exports"]
    root_dir = temp_workspace["root"]

    bootstrapper = ExportCacheBootstrapper()
    result = bootstrapper.bootstrap(
        target_dir=exports_dir, search_dirs=[exports_dir, root_dir]
    )

    assert result["restored"] is False
    assert result["archive_used"] is None
    assert result["files_extracted"] == 0
    assert result["warning"] is not None


def test_bootstrap_graceful_fallback_corrupted_zip(temp_workspace):
    exports_dir = temp_workspace["exports"]

    corrupted_zip = os.path.join(exports_dir, "exports_canonical.zip")
    with open(corrupted_zip, "w") as f:
        f.write("corrupted data not a zip")

    bootstrapper = ExportCacheBootstrapper()
    result = bootstrapper.bootstrap(target_dir=exports_dir, search_dirs=[exports_dir])

    assert result["restored"] is False
    assert result["archive_used"] == corrupted_zip
    assert result["files_extracted"] == 0
    assert result["warning"] is not None
