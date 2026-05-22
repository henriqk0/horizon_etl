import inspect
import os


def patch_prefect_task_run_payloads() -> bool:
    """Patch older Prefect clients to send task runs as JSON objects."""

    try:
        import prefect
        import prefect.states
        from prefect.client.orchestration import PrefectClient, SyncPrefectClient
        from prefect.client.schemas import TaskRun
        from prefect.client.schemas.actions import TaskRunCreate
        from prefect.client.schemas.objects import TaskRunPolicy
    except Exception:
        return False

    def needs_patch(method) -> bool:
        if getattr(method, "__horizon_json_patch__", False):
            return False

        try:
            return 'post("/task_runs/", content=content)' in inspect.getsource(method)
        except Exception:
            return False

    async def create_task_run_async(
        self,
        task,
        flow_run_id,
        dynamic_key,
        id=None,
        name=None,
        extra_tags=None,
        state=None,
        task_inputs=None,
    ):
        tags = set(task.tags).union(extra_tags or [])

        if state is None:
            state = prefect.states.Pending()

        retry_delay = task.retry_delay_seconds
        if isinstance(retry_delay, list):
            retry_delay = [int(rd) for rd in retry_delay]
        elif isinstance(retry_delay, float):
            retry_delay = int(retry_delay)

        task_run_data = TaskRunCreate(
            id=id,
            name=name,
            flow_run_id=flow_run_id,
            task_key=task.task_key,
            dynamic_key=str(dynamic_key),
            tags=list(tags),
            task_version=task.version,
            empirical_policy=TaskRunPolicy(
                retries=task.retries,
                retry_delay=retry_delay,
                retry_jitter_factor=task.retry_jitter_factor,
            ),
            state=prefect.states.to_state_create(state),
            task_inputs=task_inputs or {},
        )
        payload = task_run_data.model_dump(
            mode="json",
            exclude={"id"} if id is None else None,
        )

        response = await self._client.post("/task_runs/", json=payload)
        return TaskRun.model_validate(response.json())

    def create_task_run_sync(
        self,
        task,
        flow_run_id,
        dynamic_key,
        id=None,
        name=None,
        extra_tags=None,
        state=None,
        task_inputs=None,
    ):
        tags = set(task.tags).union(extra_tags or [])

        if state is None:
            state = prefect.states.Pending()

        retry_delay = task.retry_delay_seconds
        if isinstance(retry_delay, list):
            retry_delay = [int(rd) for rd in retry_delay]
        elif isinstance(retry_delay, float):
            retry_delay = int(retry_delay)

        task_run_data = TaskRunCreate(
            id=id,
            name=name,
            flow_run_id=flow_run_id,
            task_key=task.task_key,
            dynamic_key=str(dynamic_key),
            tags=list(tags),
            task_version=task.version,
            empirical_policy=TaskRunPolicy(
                retries=task.retries,
                retry_delay=retry_delay,
                retry_jitter_factor=task.retry_jitter_factor,
            ),
            state=prefect.states.to_state_create(state),
            task_inputs=task_inputs or {},
        )
        payload = task_run_data.model_dump(
            mode="json",
            exclude={"id"} if id is None else None,
        )

        response = self._client.post("/task_runs/", json=payload)
        return TaskRun.model_validate(response.json())

    patched = False

    if needs_patch(PrefectClient.create_task_run):
        create_task_run_async.__horizon_json_patch__ = True
        PrefectClient.create_task_run = create_task_run_async
        patched = True

    if needs_patch(SyncPrefectClient.create_task_run):
        create_task_run_sync.__horizon_json_patch__ = True
        SyncPrefectClient.create_task_run = create_task_run_sync
        patched = True

    return patched


def disable_prefect_events_client() -> bool:
    """Route Prefect event traffic to a no-op client when supported."""

    try:
        import prefect.events.worker as events_worker
        from prefect.events.clients import NullEventsClient
    except Exception:
        return False

    worker_cls = getattr(events_worker, "EventsWorker", None)
    if worker_cls is None:
        return False

    set_client_override = getattr(worker_cls, "set_client_override", None)
    if callable(set_client_override):
        set_client_override(NullEventsClient)
        return True

    if hasattr(worker_cls, "_client_override"):
        try:
            worker_cls._client_override = (NullEventsClient, tuple())
            return True
        except Exception:
            return False

    return False


def bootstrap_local_prefect() -> None:
    """Disable noisy Prefect API side channels for local CLI runs."""

    if os.getenv("HORIZON_QUIET_PREFECT") not in {"1", "true", "TRUE"}:
        return

    os.environ.setdefault("PREFECT_LOGGING_TO_API_ENABLED", "false")
    os.environ.setdefault("PREFECT_CLIENT_SERVER_VERSION_CHECK_ENABLED", "false")

    try:
        import prefect.events.utilities as events_utilities
    except Exception:
        events_utilities = None

    try:
        import prefect.events.worker as events_worker
    except Exception:
        events_worker = None

    if events_worker is not None and hasattr(events_worker, "should_emit_events"):
        events_worker.should_emit_events = lambda: False

    if events_utilities is not None and hasattr(events_utilities, "should_emit_events"):
        events_utilities.should_emit_events = lambda: False

    patch_prefect_task_run_payloads()

    # Local ETL execution should proceed even if Prefect internals change.
    disable_prefect_events_client()
