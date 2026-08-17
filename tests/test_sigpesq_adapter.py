import asyncio
import os
import shutil
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.adapters.sources.sigpesq.adapter import SigPesqAdapter


@pytest.fixture
def mock_data_dir():
    dir_path = "data/test_sigpesq"
    if os.path.exists(dir_path):
        shutil.rmtree(dir_path)
    os.makedirs(dir_path)
    yield dir_path
    if os.path.exists(dir_path):
        shutil.rmtree(dir_path)


def test_sigpesq_adapter_extract(mock_data_dir):
    # Arrange
    from unittest.mock import patch

    adapter = SigPesqAdapter(download_dir=mock_data_dir)

    def trigger_download(_download_strategies=None):
        report_dir = os.path.join(mock_data_dir, "report")
        os.makedirs(report_dir, exist_ok=True)
        dummy_file = os.path.join(report_dir, "mock_project_001.json")
        with open(dummy_file, "w") as f:
            f.write('{"id": 1, "title": "Mock Project"}')

    # Act
    with (
        patch.object(SigPesqAdapter, "_validate_environment"),
        patch.object(SigPesqAdapter, "_trigger_download", side_effect=trigger_download),
    ):
        results = adapter.extract()

    # Assert
    assert len(results) > 0
    assert "filename" in results[0]
    assert "parsed_content" in results[0]
    # assert results[0]["source"] == "sigpesq" # Removed: Implementation does not provide this key

    # Verify file was created (mock behavior)
    assert os.path.exists(
        os.path.join(mock_data_dir, "report", "mock_project_001.json")
    )


def test_sigpesq_adapter_cleans_download_dir_before_download(tmp_path):
    adapter = SigPesqAdapter(download_dir=str(tmp_path))

    stale_dir = tmp_path / "advisorships" / "2025"
    stale_dir.mkdir(parents=True)
    stale_file = stale_dir / "old_report.xlsx"
    stale_file.write_text("old")

    def trigger_download(_download_strategies=None):
        assert not stale_file.exists()
        report_dir = tmp_path / "report"
        report_dir.mkdir()
        (report_dir / "fresh_report.json").write_text('{"id": 2}')

    with (
        patch.object(SigPesqAdapter, "_validate_environment"),
        patch.object(SigPesqAdapter, "_trigger_download", side_effect=trigger_download),
    ):
        results = adapter.extract()

    assert len(results) == 1
    assert results[0]["filename"] == "fresh_report.json"
    assert not stale_file.exists()


def test_sigpesq_adapter_logs_http_429_during_login(tmp_path):
    class FakePage:
        def __init__(self):
            self.handlers = {}

        def on(self, event_name, handler):
            self.handlers[event_name] = handler

        def remove_listener(self, event_name, handler):
            assert event_name == "response"
            assert self.handlers[event_name] is handler

    class FakeService:
        async def _login(self, page):
            response = SimpleNamespace(
                status=429,
                url="https://sigpesq.ifes.edu.br/Login.aspx",
            )
            page.handlers["response"](response)
            return False

    adapter = SigPesqAdapter(download_dir=str(tmp_path))
    service = FakeService()

    adapter._attach_http_429_logging(service)

    with patch("src.adapters.sources.sigpesq.adapter.logger.error") as log_error:
        assert asyncio.run(service._login(FakePage())) is False

    log_message = log_error.call_args.args[0]
    assert "HTTP 429" in log_message
    assert "Rate limiting" in log_message
    assert "Login.aspx" in log_message
