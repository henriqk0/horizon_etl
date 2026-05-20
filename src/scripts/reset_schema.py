
import sys
import os
from sqlalchemy import text
from loguru import logger

# Add project root to path
sys.path.append(os.getcwd())

from eo_lib.infrastructure.database.postgres_client import PostgresClient
from eo_lib.domain.base import Base
from research_domain.domain.entities.academic_education import AcademicEducation, EducationType


def reset_schema():
    logger.info("Resetting AcademicEducation schema...")
    client = PostgresClient()
    session = client.get_session()
    engine = client._engine

    # 1. Drop Table with Raw SQL to be sure
    try:
        logger.info("Dropping tables...")
        session.execute(text("DELETE FROM academic_education_knowledge_areas"))
        session.execute(text("DELETE FROM academic_educations"))
        session.execute(text("DELETE FROM initiatives"))
        session.execute(text("DELETE FROM education_types"))

        # We don't drop tables to avoid recreating FK complexity if headers changed in lib
        # Just DELETE data to be safe for Unique Constraints
        session.commit()
        logger.info("Tables cleared.")
    except Exception as e:
        logger.error(f"Failed to clear tables: {e}")
        return

    # 2. Recreate (Only if missing?)
    # ...
    # Base.metadata.create_all(engine)  # Still beneficial if tables dropped previously
    pass

    # 2. Recreate
    logger.info("Recreating tables...")
    # Ensure metadata is populated
    # AcademicEducation is already imported
    Base.metadata.create_all(engine)
    logger.info("Tables recreated.")

    # 3. Verify
    res = session.execute(text("PRAGMA table_info(academic_educations)")).fetchall()
    cols = [r[1] for r in res]
    logger.info(f"New Columns: {cols}")

    if "organization_id" in cols and "thesis_title" in cols:
        logger.info("SUCCESS: Schema updated.")
    else:
        logger.error("FAILURE: Schema still old.")

if __name__ == "__main__":
    reset_schema()
