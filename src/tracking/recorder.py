import hashlib
import json
import re
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any, Iterable, Optional

from sqlalchemy.exc import IntegrityError

from src.tracking.context import current_ingestion_run_id, current_source_system
from src.tracking.controllers import (
    AttributeAssertionController,
    EntityChangeLogController,
    EntityMatchController,
    IngestionRunController,
    SourceRecordController,
)

# Sensitive field patterns that should be sanitized before storage (LGPD compliance)
# These patterns match fields containing personal data that must not be stored
SENSITIVE_FIELD_PATTERNS = re.compile(
    r"(?i)"
    r"(?:"
    r"orientador_email|"  # Supervisor email
    r"celular_orientador|"  # Supervisor phone
    r"orientado_email|"  # Student email
    r"orientado_cpf|"  # Student CPF (Brazilian ID)
    r"celular_orientado|"  # Student phone
    r"cpf|"  # CPF anywhere
    r"email|"  # Generic email (too broad, be careful)
    r"celular|"  # Generic phone
    r"telefone"  # Generic phone
    r")",
    re.IGNORECASE,
)

# Fields that are explicitly sensitive and MUST be removed
EXPLICIT_SENSITIVE_FIELDS = frozenset({
    "OrientadorEmail",
    "CelularOrientador",
    "OrientadoEmail",
    "OrientadoCpf",
    "CelularOrientado",
    "cpf",
    "CPF",
})


def _json_default(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(nested) for key, nested in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


# Email pattern to detect and redact emails in string values
EMAIL_PATTERN = re.compile(
    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
    re.IGNORECASE,
)


def _redact_email(value: str) -> str:
    """Redacts email addresses from a string, replacing with [REDACTED]."""
    return EMAIL_PATTERN.sub("[REDACTED]", value)


def sanitize_payload(payload: Any) -> Any:
    """
    Removes sensitive personal data from payload before storing in tracking tables.
    This ensures LGPD compliance by not storing PII in the tracking audit trail.
    """
    if not isinstance(payload, dict):
        # Also sanitize string values that might contain emails
        if isinstance(payload, str) and EMAIL_PATTERN.search(payload):
            return _redact_email(payload)
        return payload

    sanitized = {}
    for key, value in payload.items():
        # Skip explicitly sensitive fields
        if key in EXPLICIT_SENSITIVE_FIELDS:
            continue
        # Skip fields matching sensitive patterns (except for safe exceptions)
        if SENSITIVE_FIELD_PATTERNS.match(key):
            # Allow some safe fields that happen to match patterns
            if key.lower() in ("email", "celular", "telefone"):
                # Check if it's actually a generic institutional field - still remove
                pass
            else:
                continue

        # Recursively sanitize nested dicts
        if isinstance(value, dict):
            sanitized[key] = sanitize_payload(value)
        elif isinstance(value, (list, tuple)):
            sanitized[key] = [
                sanitize_payload(item) if isinstance(item, dict) else (
                    _redact_email(item) if isinstance(item, str) else item
                )
                for item in value
            ]
        elif isinstance(value, str):
            # Also redact emails in string values
            sanitized[key] = _redact_email(value)
        else:
            sanitized[key] = value

    return sanitized


def stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False, default=_json_default)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class TrackingRecorder:
    def __init__(self):
        self._ingestion_run_controller_cls = IngestionRunController
        self._source_record_controller_cls = SourceRecordController
        self._entity_match_controller_cls = EntityMatchController
        self._attribute_assertion_controller_cls = AttributeAssertionController
        self._entity_change_log_controller_cls = EntityChangeLogController

    @contextmanager
    def _controller(self, controller_cls, legacy_attr: str | None = None):
        close_session = False
        if legacy_attr and hasattr(self, legacy_attr):
            controller = getattr(self, legacy_attr)
        else:
            controller = controller_cls()
            close_session = True

        session = controller._service._repository._session
        try:
            yield controller
        except Exception:
            session.rollback()
            raise
        finally:
            if close_session:
                session.close()

    def _rollback_legacy_sessions(self) -> None:
        seen_sessions: set[int] = set()
        for legacy_attr in (
            "ingestion_run_ctrl",
            "source_record_ctrl",
            "entity_match_ctrl",
            "attribute_assertion_ctrl",
            "entity_change_log_ctrl",
        ):
            controller = getattr(self, legacy_attr, None)
            if controller is None:
                continue
            session = controller._service._repository._session
            if id(session) in seen_sessions:
                continue
            seen_sessions.add(id(session))
            try:
                session.rollback()
            except Exception:
                pass

    @contextmanager
    def run_context(self, *, source_system: str, flow_name: str, notes: Optional[str] = None):
        with self._controller(
            getattr(self, "_ingestion_run_controller_cls", IngestionRunController),
            legacy_attr="ingestion_run_ctrl",
        ) as controller:
            run = controller.create_run(
                source_system=source_system,
                flow_name=flow_name,
                notes=notes,
            )
            run_id = run.id

        run_token = current_ingestion_run_id.set(run_id)
        source_token = current_source_system.set(source_system)
        try:
            yield SimpleNamespace(id=run_id, source_system=source_system, flow_name=flow_name)
            with self._controller(
                getattr(self, "_ingestion_run_controller_cls", IngestionRunController),
                legacy_attr="ingestion_run_ctrl",
            ) as controller:
                controller.finalize_run(run_id, status="success")
        except Exception as exc:
            self._rollback_legacy_sessions()
            with self._controller(
                getattr(self, "_ingestion_run_controller_cls", IngestionRunController),
                legacy_attr="ingestion_run_ctrl",
            ) as controller:
                controller.finalize_run(run_id, status="failed", notes=str(exc))
            raise
        finally:
            current_ingestion_run_id.reset(run_token)
            current_source_system.reset(source_token)

    def has_active_run(self) -> bool:
        return current_ingestion_run_id.get() is not None

    def record_source_record(
        self,
        *,
        source_entity_type: str,
        payload: Any,
        source_record_id: Optional[str] = None,
        source_file: Optional[str] = None,
        source_path: Optional[str] = None,
    ):
        run_id = current_ingestion_run_id.get()
        source_system = current_source_system.get()
        if not run_id or not source_system:
            return None

        # Sanitize payload to remove sensitive PII before storing (LGPD compliance)
        sanitized_payload = sanitize_payload(payload)
        payload_hash = stable_hash(sanitized_payload)
        with self._controller(
            getattr(self, "_source_record_controller_cls", SourceRecordController),
            legacy_attr="source_record_ctrl",
        ) as controller:
            try:
                return controller.create_source_record(
                    ingestion_run_id=run_id,
                    source_system=source_system,
                    source_entity_type=source_entity_type,
                    source_record_id=source_record_id,
                    source_file=source_file,
                    source_path=source_path,
                    raw_payload_json=_json_safe(sanitized_payload),
                    payload_hash=payload_hash,
                )
            except IntegrityError:
                session = controller._service._repository._session
                session.rollback()
                return (
                    session.query(controller._service._repository._entity_type)
                    .filter_by(
                        ingestion_run_id=run_id,
                        source_system=source_system,
                        source_entity_type=source_entity_type,
                        source_record_id=source_record_id,
                        payload_hash=payload_hash,
                    )
                    .first()
                )

    def record_entity_match(
        self,
        *,
        source_record_id: Optional[int],
        canonical_entity_type: str,
        canonical_entity_id: int,
        match_strategy: str,
        match_confidence: Optional[float] = None,
    ):
        if not source_record_id:
            return None

        with self._controller(
            getattr(self, "_entity_match_controller_cls", EntityMatchController),
            legacy_attr="entity_match_ctrl",
        ) as controller:
            try:
                return controller.create_match(
                    source_record_id=source_record_id,
                    canonical_entity_type=canonical_entity_type,
                    canonical_entity_id=canonical_entity_id,
                    match_strategy=match_strategy,
                    match_confidence=match_confidence,
                )
            except IntegrityError:
                session = controller._service._repository._session
                session.rollback()
                return None

    def record_attribute_assertions(
        self,
        *,
        source_record_id: Optional[int],
        canonical_entity_type: str,
        canonical_entity_id: int,
        selected_attributes: dict[str, Any],
        selection_reason: str,
    ) -> None:
        if not source_record_id:
            return

        for attribute_name, value in selected_attributes.items():
            with self._controller(
                getattr(
                    self,
                    "_attribute_assertion_controller_cls",
                    AttributeAssertionController,
                ),
                legacy_attr="attribute_assertion_ctrl",
            ) as controller:
                try:
                    controller.create_assertion(
                        source_record_id=source_record_id,
                        canonical_entity_type=canonical_entity_type,
                        canonical_entity_id=canonical_entity_id,
                        attribute_name=attribute_name,
                        value_hash=stable_hash(value),
                        value_json=_json_safe(value),
                        is_selected=True,
                        selection_reason=selection_reason,
                    )
                except IntegrityError:
                    session = controller._service._repository._session
                    session.rollback()

    def record_change(
        self,
        *,
        source_record_id: Optional[int],
        canonical_entity_type: str,
        canonical_entity_id: int,
        operation: str,
        changed_fields: Iterable[str],
        before: Optional[dict[str, Any]] = None,
        after: Optional[dict[str, Any]] = None,
        reason: Optional[str] = None,
    ) -> None:
        run_id = current_ingestion_run_id.get()
        if not run_id:
            return

        # Sanitize before/after to remove sensitive PII (LGPD compliance)
        sanitized_before = sanitize_payload(before) if before else None
        sanitized_after = sanitize_payload(after) if after else None

        with self._controller(
            getattr(
                self,
                "_entity_change_log_controller_cls",
                EntityChangeLogController,
            ),
            legacy_attr="entity_change_log_ctrl",
        ) as controller:
            controller.create_change_log(
                ingestion_run_id=run_id,
                source_record_id=source_record_id,
                canonical_entity_type=canonical_entity_type,
                canonical_entity_id=canonical_entity_id,
                operation=operation,
                changed_fields_json=_json_safe(list(changed_fields)),
                before_json=_json_safe(sanitized_before),
                after_json=_json_safe(sanitized_after),
                reason=reason,
            )


tracking_recorder = TrackingRecorder()
