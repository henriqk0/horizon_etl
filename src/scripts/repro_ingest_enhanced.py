import os
import sys

from loguru import logger
from sqlalchemy import text

# Add project root to path
sys.path.append(os.getcwd())

from eo_lib import InitiativeController, PersonController
from research_domain.controllers.academic_education_controller import (
    AcademicEducationController,
)

from src.core.logic.entity_manager import EntityManager
from src.flows.lattes.projects import ingest_file_task

# Configure logger
logger.remove()
logger.add(sys.stdout, level="INFO")


def run_repro():
    print("Initializing DB Schema (which should trigger drop/create in flow)...")

    # We rely on the flow to handle the table drop now, but we need to setup context
    init_ctrl = InitiativeController()
    person_ctrl = PersonController()
    entity_manager = EntityManager(init_ctrl, person_ctrl)

    # Force table update logic if it was inside the flow main, but since we call task directly we might miss it
    # We should run the flow logic part that does init
    try:
        from eo_lib.domain.base import Base
        from research_domain.domain.entities.academic_education import AcademicEducation

        engine = init_ctrl.client.engine
        AcademicEducation.__table__.drop(engine, checkfirst=True)
        Base.metadata.create_all(engine)
        print("Recreated academic_educations table.")
    except Exception as e:
        print(f"Schema update failed: {e}")

    target_file = (
        "data/lattes_json/00_Paulo-Sergio-dos-Santos-Junior_8400407353673370.json"
    )

    print(f"Running ingestion for {target_file}...")
    ingest_file_task.fn(target_file, entity_manager)

    # Verify content
    print("Verifying data...")
    from eo_lib.infrastructure.database.postgres_client import PostgresClient

    client = PostgresClient()
    session = client.get_session()

    # Check if table exists and has columns
    try:
        result = session.execute(
            text(
                "SELECT degree, institution, organization_id, thesis_title FROM academic_educations WHERE researcher_id = 604"
            )
        ).fetchall()
        for row in result:
            print(f"Deg: {row[0]}, Inst: {row[1]}, OrgID: {row[2]}, Theta: {row[3]}")
    except Exception as e:
        print(f"Verification Failed: {e}")


if __name__ == "__main__":
    run_repro()
