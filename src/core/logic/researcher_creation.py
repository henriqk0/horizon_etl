"""Helpers for creating researchers across inconsistent library versions."""

from typing import Any, Optional

from loguru import logger
from sqlalchemy import text

from src.core.logic.pii_anonymizer import anonymize_person_data


def create_researcher_with_resume_fallback(
    researcher_ctrl,
    *,
    name: str,
    identification_id: Optional[str] = None,
    emails: Optional[list[str]] = None,
):
    """Create a researcher, tolerating controller/service signature mismatches.

    Some `research-domain` controller versions still forward `resume=None` to
    an `eo-lib` service implementation that no longer accepts that keyword.
    When that specific mismatch happens, call the underlying service method
    without `resume`, then ensure the joined-table `researchers` row exists.
    """

    pii = anonymize_person_data({"identification_id": identification_id})
    identification_id = pii["identification_id"]
    if emails:
        emails = [anonymize_person_data({"email": e})["email"] for e in emails if e] or None

    try:
        return researcher_ctrl.create_researcher(
            name=name,
            emails=emails,
            identification_id=identification_id,
        )
    except Exception as exc:
        # Handle UNIQUE constraint conflict (e.g., from concurrent Prefect tasks)
        if _is_unique_constraint_error(exc):
            logger.debug(
                f"Researcher '{name}' (ID: {identification_id}) already exists due to concurrent insert. Fetching existing."
            )
            _rollback_session(researcher_ctrl)
            existing = _find_researcher_by_identification_id(researcher_ctrl, identification_id)
            if existing:
                return existing
            # If fetch fails, re-raise
            raise
        # Handle PersonEmail type mismatch - try without emails
        if _is_person_email_type_mismatch(exc) and emails:
            logger.debug(
                f"Falling back to researcher creation without relationship-bound emails for '{name}'."
            )
            _rollback_session(researcher_ctrl)
            researcher = researcher_ctrl.create_researcher(
                name=name,
                emails=None,
                identification_id=identification_id,
            )
            _ensure_researcher_row(researcher_ctrl, researcher.id)
            _ensure_person_emails(researcher_ctrl, researcher.id, emails)
            try:
                return researcher_ctrl.get_by_id(researcher.id)
            except Exception:
                return researcher
        raise
    except TypeError as exc:
        if "resume" not in str(exc):
            raise

        logger.debug(
            f"Falling back to direct Researcher creation for '{name}' due to controller/service signature mismatch."
        )
        researcher = researcher_ctrl._service.create_with_details(
            name=name,
            emails=emails,
            identification_id=identification_id,
        )
        _ensure_researcher_row(researcher_ctrl, researcher.id)

        try:
            return researcher_ctrl.get_by_id(researcher.id)
        except Exception:
            return researcher


def _ensure_researcher_row(researcher_ctrl, person_id: Optional[int]) -> None:
    """Backfill joined-table inheritance row when only `persons` was inserted."""
    if not person_id:
        return

    try:
        session = researcher_ctrl._service._repository._session
        exists = session.execute(
            text("SELECT 1 FROM researchers WHERE id = :rid"),
            {"rid": person_id},
        ).scalar()
        if not exists:
            session.execute(
                text("INSERT INTO researchers (id) VALUES (:rid)"),
                {"rid": person_id},
            )
            session.commit()
    except Exception:
        try:
            session.rollback()
        except Exception:
            pass
        raise


def _ensure_person_emails(
    researcher_ctrl,
    person_id: Optional[int],
    emails: Optional[list[str]],
) -> None:
    if not person_id or not emails:
        return

    session = researcher_ctrl._service._repository._session
    try:
        for email in emails:
            if not email:
                continue
            email = anonymize_person_data({"email": email})["email"]
            exists = session.execute(
                text(
                    """
                    SELECT 1
                    FROM person_emails
                    WHERE person_id = :pid
                      AND lower(email) = lower(:email)
                    """
                ),
                {"pid": person_id, "email": email},
            ).scalar()
            if not exists:
                session.execute(
                    text(
                        """
                        INSERT INTO person_emails (person_id, email)
                        VALUES (:pid, :email)
                        """
                    ),
                    {"pid": person_id, "email": email},
                )
        session.commit()
    except Exception:
        try:
            session.rollback()
        except Exception:
            pass
        raise


def _rollback_session(researcher_ctrl) -> None:
    try:
        researcher_ctrl._service._repository._session.rollback()
    except Exception:
        pass


def _is_person_email_type_mismatch(exc: Exception) -> bool:
    message = str(exc)
    return "PersonEmail.person" in message and "Expected an object of type" in message


def _is_unique_constraint_error(exc: Exception) -> bool:
    """Check if exception is a UNIQUE constraint violation."""
    message = str(exc).lower()
    return (
        "unique" in message or
        "duplicate" in message or
        "constraint" in message and "failed" in message
    )


def _find_researcher_by_identification_id(researcher_ctrl, identification_id: Optional[str]) -> Optional[Any]:
    """Find an existing researcher by identification_id."""
    if not identification_id:
        return None
    try:
        all_researchers = researcher_ctrl.get_all()
        for r in all_researchers:
            if getattr(r, "identification_id", None) == identification_id:
                return r
    except Exception:
        pass
    return None
