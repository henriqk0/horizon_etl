import asyncio
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from prefect.client.orchestration import PrefectClient, SyncPrefectClient
from prefect.client.schemas import TaskRun
from prefect.events.clients import NullEventsClient
from prefect.events.worker import EventsWorker

from src.flows.prefect_runtime import configure_prefect_runtime
from src.prefect_runtime import (
    disable_prefect_events_client,
    patch_prefect_task_run_payloads,
)


def test_configure_prefect_runtime_disables_events_for_local_server(monkeypatch):
    monkeypatch.setenv("PREFECT_API_URL", "http://127.0.0.1:4200/api")
    monkeypatch.delenv("PREFECT_API_KEY", raising=False)

    with patch(
        "src.flows.prefect_runtime.disable_prefect_events_client", return_value=True
    ) as disable:
        assert configure_prefect_runtime() is True
        disable.assert_called_once_with()


def test_configure_prefect_runtime_keeps_events_for_non_local_urls(monkeypatch):
    monkeypatch.setenv(
        "PREFECT_API_URL", "https://api.prefect.cloud/api/accounts/x/workspaces/y"
    )
    monkeypatch.delenv("PREFECT_API_KEY", raising=False)

    with patch("src.flows.prefect_runtime.disable_prefect_events_client") as disable:
        assert configure_prefect_runtime() is False
        disable.assert_not_called()


def test_disable_prefect_events_client_falls_back_to_private_override(monkeypatch):
    monkeypatch.delattr(EventsWorker, "set_client_override", raising=False)
    monkeypatch.setattr(EventsWorker, "_client_override", None, raising=False)

    assert disable_prefect_events_client() is True
    assert EventsWorker._client_override == (NullEventsClient, tuple())


def test_configure_prefect_runtime_keeps_events_when_api_key_is_present(monkeypatch):
    monkeypatch.setenv("PREFECT_API_URL", "http://127.0.0.1:4200/api")
    monkeypatch.setenv("PREFECT_API_KEY", "token")

    with patch("src.flows.prefect_runtime.disable_prefect_events_client") as disable:
        assert configure_prefect_runtime() is False
        disable.assert_not_called()


def test_prefect_task_run_patch_uses_json_payload_for_async_client(monkeypatch):
    patch_prefect_task_run_payloads()

    class DummyResponse:
        def json(self):
            return {"ok": True}

    class DummyAsyncHttpClient:
        def __init__(self):
            self.calls = []

        async def post(self, url, **kwargs):
            self.calls.append((url, kwargs))
            return DummyResponse()

    monkeypatch.setattr(
        TaskRun,
        "model_validate",
        classmethod(lambda cls, data: data),
    )

    task = SimpleNamespace(
        tags={"base-tag"},
        retry_delay_seconds=1.0,
        task_key="task-key",
        version="v-test",
        retries=2,
        retry_jitter_factor=None,
    )
    http_client = DummyAsyncHttpClient()
    client = SimpleNamespace(_client=http_client)

    result = asyncio.run(
        PrefectClient.create_task_run(
            client,
            task=task,
            flow_run_id=uuid4(),
            dynamic_key="dyn-1",
            extra_tags=["extra-tag"],
            task_inputs={},
        )
    )

    assert result == {"ok": True}
    assert len(http_client.calls) == 1
    url, kwargs = http_client.calls[0]
    assert url == "/task_runs/"
    assert "json" in kwargs
    assert "content" not in kwargs
    assert kwargs["json"]["task_key"] == "task-key"
    assert kwargs["json"]["dynamic_key"] == "dyn-1"
    assert set(kwargs["json"]["tags"]) == {"base-tag", "extra-tag"}


def test_prefect_task_run_patch_uses_json_payload_for_sync_client(monkeypatch):
    patch_prefect_task_run_payloads()

    class DummyResponse:
        def json(self):
            return {"ok": True}

    class DummySyncHttpClient:
        def __init__(self):
            self.calls = []

        def post(self, url, **kwargs):
            self.calls.append((url, kwargs))
            return DummyResponse()

    monkeypatch.setattr(
        TaskRun,
        "model_validate",
        classmethod(lambda cls, data: data),
    )

    task = SimpleNamespace(
        tags={"base-tag"},
        retry_delay_seconds=[1, 2],
        task_key="task-key",
        version="v-test",
        retries=3,
        retry_jitter_factor=None,
    )
    http_client = DummySyncHttpClient()
    client = SimpleNamespace(_client=http_client)

    result = SyncPrefectClient.create_task_run(
        client,
        task=task,
        flow_run_id=uuid4(),
        dynamic_key="dyn-2",
        extra_tags=["extra-tag"],
        task_inputs={},
    )

    assert result == {"ok": True}
    assert len(http_client.calls) == 1
    url, kwargs = http_client.calls[0]
    assert url == "/task_runs/"
    assert "json" in kwargs
    assert "content" not in kwargs
    assert kwargs["json"]["task_key"] == "task-key"
    assert kwargs["json"]["dynamic_key"] == "dyn-2"
    assert kwargs["json"]["empirical_policy"]["retry_delay"] == [1, 2]
