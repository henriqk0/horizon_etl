from contextvars import ContextVar

current_ingestion_run_id: ContextVar[int | None] = ContextVar(
    "current_ingestion_run_id", default=None
)
current_source_system: ContextVar[str | None] = ContextVar(
    "current_source_system", default=None
)
