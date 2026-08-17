import os

import pytest

from src.flows.lattes.download import (
    ScriptLattesRuntimeError,
    clean_lattes_json_output,
    collect_lattes_ids_from_list,
    download_lattes_flow,
    prefetch_lattes_cache,
    validate_script_lattes_runtime,
)


def test_clean_lattes_json_output_removes_only_json_files(tmp_path):
    output_dir = tmp_path / "lattes_json"
    output_dir.mkdir()
    stale_json = output_dir / "old.json"
    keep_text = output_dir / "notes.txt"
    nested_dir = output_dir / "nested"
    nested_dir.mkdir()
    nested_json = nested_dir / "nested.json"

    stale_json.write_text("{}")
    keep_text.write_text("keep")
    nested_json.write_text("{}")

    removed = clean_lattes_json_output(str(output_dir))

    assert removed == 1
    assert not stale_json.exists()
    assert keep_text.exists()
    assert nested_json.exists()


def test_collect_lattes_ids_from_list_reads_16_digit_ids(tmp_path):
    list_path = tmp_path / "lattes.list"
    list_path.write_text(
        "\n".join(
            [
                "8400407353673370 , Paulo Sergio dos Santos Junior",
                "http://lattes.cnpq.br/9583314331960942 Daniel Cruz Cavalieri",
                "invalid line",
            ]
        )
    )

    assert collect_lattes_ids_from_list(str(list_path)) == [
        "8400407353673370",
        "9583314331960942",
    ]


def test_prefetch_lattes_cache_downloads_only_missing_ids(tmp_path):
    cache_dir = tmp_path / "cache"
    cached_id = "8400407353673370"
    missing_ids = ["9583314331960942", "8826584877205264"]
    downloaded = []

    cache_dir.mkdir()
    (cache_dir / cached_id).write_text("cached")

    def fake_downloader(lattes_id, target_cache_dir):
        downloaded.append((lattes_id, target_cache_dir))
        (cache_dir / lattes_id).write_text("downloaded")

    result = prefetch_lattes_cache(
        [cached_id, *missing_ids],
        str(cache_dir),
        max_workers=2,
        downloader=fake_downloader,
    )

    assert result == missing_ids
    assert sorted(downloaded) == sorted(
        (lattes_id, str(cache_dir)) for lattes_id in missing_ids
    )


def test_validate_script_lattes_runtime_rejects_missing_playwright_chromium(
    monkeypatch,
):
    """validate_script_lattes_runtime no longer compares chromedriver/chrome
    versions (that scriptLattes-driven implementation was replaced by a
    Playwright-based one) — it now only requires Playwright's bundled
    Chromium to be installed."""
    monkeypatch.setattr(
        "src.flows.lattes.download._check_playwright_chromium", lambda: False
    )

    with pytest.raises(ScriptLattesRuntimeError, match="Chromium is not installed"):
        validate_script_lattes_runtime()


def test_validate_script_lattes_runtime_accepts_installed_playwright_chromium(
    monkeypatch,
):
    monkeypatch.setattr(
        "src.flows.lattes.download._check_playwright_chromium", lambda: True
    )

    assert validate_script_lattes_runtime() == "playwright-chromium"


def test_download_lattes_flow(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    # The flow now sources its researcher list from the DB (get_researchers_from_db
    # -> generate_list) instead of reading a pre-existing data/lattes_run/lattes.list
    # file, and validate_script_lattes_runtime/prefetch_lattes_cache/
    # run_script_lattes_real no longer take a chrome_binary argument (the
    # scriptLattes/chromedriver runtime was replaced by Playwright). See
    # src/flows/lattes/download.py.
    def fake_get_researchers_from_db():
        return [
            {"name": "Paulo Sergio dos Santos Junior", "lattes_id": "8400407353673370"},
            {"name": "Daniel Cruz Cavalieri", "lattes_id": "9583314331960942"},
        ]

    def fake_generate_list(researchers):
        list_path = tmp_path / "cache" / "lattes.list"
        list_path.parent.mkdir(parents=True, exist_ok=True)
        list_path.write_text(
            "\n".join(f"{r['lattes_id']} , {r['name']}" for r in researchers)
        )
        return str(list_path)

    prefetch_calls = []

    def fake_prefetch(lattes_ids, cache_dir, max_workers):
        prefetch_calls.append((lattes_ids, cache_dir, max_workers))
        return lattes_ids

    def fake_run_script_lattes(config_path):
        output_dir = tmp_path / "data" / "lattes_json"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "00_Paulo_8400407353673370.json").write_text("{}")
        (output_dir / "01_Daniel_9583314331960942.json").write_text("{}")

    monkeypatch.setenv("HORIZON_LATTES_DOWNLOAD_WORKERS", "2")
    monkeypatch.setattr(
        "src.flows.lattes.download.get_researchers_from_db",
        fake_get_researchers_from_db,
    )
    monkeypatch.setattr("src.flows.lattes.download.generate_list", fake_generate_list)
    monkeypatch.setattr(
        "src.flows.lattes.download.validate_script_lattes_runtime",
        lambda: "playwright-chromium",
    )
    monkeypatch.setattr(
        "src.flows.lattes.download.prefetch_lattes_cache", fake_prefetch
    )
    monkeypatch.setattr(
        "src.flows.lattes.download.run_script_lattes_real", fake_run_script_lattes
    )

    # Execute Flow
    download_lattes_flow()

    # Verify
    assert os.path.exists("cache/lattes.config")
    assert os.path.isdir("data/lattes_json")
    assert prefetch_calls == [
        (
            ["8400407353673370", "9583314331960942"],
            str(tmp_path / "cache"),
            2,
        )
    ]

    # Check if a JSON file was created (based on the mock data in the flow)
    # The flow mocks IDs, but scriptLattes might prefix them with numbers/names
    assert any("8400407353673370" in f for f in os.listdir("data/lattes_json"))
    assert any("9583314331960942" in f for f in os.listdir("data/lattes_json"))
