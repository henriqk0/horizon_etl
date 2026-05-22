import os  # noqa E402
import sys  # noqa E402

from loguru import logger  # noqa E402
from sqlalchemy import text  # noqa E402

sys.path.append(os.getcwd())

from eo_lib import InitiativeController, PersonController
from eo_lib.infrastructure.database.postgres_client import PostgresClient

from src.core.logic.entity_manager import EntityManager
from src.flows.lattes.projects import ingest_file_task

# Configure logger
logger.remove()
logger.add(sys.stdout, level="INFO")


def run_repro():
    print("Running Strict Ingestion Repro...")

    init_ctrl = InitiativeController()
    person_ctrl = PersonController()
    entity_manager = EntityManager(init_ctrl, person_ctrl)

    target_file = (
        "data/lattes_json/00_Paulo-Sergio-dos-Santos-Junior_8400407353673370.json"
    )

    # 1. Check if tables exist
    client = PostgresClient()
    s = client.get_session()
    try:
        s.execute(text("SELECT count(*) FROM education_types"))
    except Exception as e:
        print(f"Table check failed: {e}")
        # Try to run reset schema logic here if needed, but assuming check passed?

    print(f"Ingesting {target_file}...")
    ingest_file_task.fn(target_file, entity_manager)

    # 2. Verify
    print("Verifying data...")
    try:
        res = s.execute(text("SELECT count(*) FROM academic_educations")).scalar()
        print(f"AcademicEducation Count: {res}")

        res_types = s.execute(text("SELECT * FROM education_types")).fetchall()
        print(f"EducationTypes: {res_types}")

        res_edu = s.execute(
            text(
                "SELECT researcher_id, title, institution_id, education_type_id FROM academic_educations"
            )
        ).fetchall()
        for r in res_edu:
            print(f"Row: {r}")

    except Exception as e:
        print(f"Verification Failed: {e}")


if __name__ == "__main__":
    run_repro()
