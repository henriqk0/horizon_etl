import os  # noqa E402
import sys  # noqa E402

from loguru import logger  # noqa E402
from sqlalchemy import inspect  # noqa E402

sys.path.append(os.getcwd())

from eo_lib.domain.base import Base
from eo_lib.infrastructure.database.postgres_client import PostgresClient

# Import all models to register them  # Import others if needed?


def debug_metadata():
    logger.info("Debugging Metadata...")

    # 1. Check Metadata Registration
    tables = list(Base.metadata.tables.keys())
    logger.info(f"Registered Tables in Base.metadata: {tables}")

    if "education_types" not in tables:
        logger.error("CRITICAL: education_types NOT in metadata!")

    if "academic_educations" not in tables:
        logger.error("CRITICAL: academic_educations NOT in metadata!")

    # 2. Check Database
    client = PostgresClient()
    engine = client._engine
    inspector = inspect(engine)

    db_tables = inspector.get_table_names()
    logger.info(f"Tables in Database (Initial): {db_tables}")

    # 3. Create All
    logger.info("Running create_all...")
    try:
        Base.metadata.create_all(engine)
        logger.info("create_all executed.")
    except Exception as e:
        logger.error(f"create_all failed: {e}")

    # 4. Check Database Again
    db_tables_after = inspector.get_table_names()
    logger.info(f"Tables in Database (After): {db_tables_after}")

    if "education_types" in db_tables_after:
        logger.info("SUCCESS: education_types exists.")
    else:
        logger.error("FAILURE: education_types missing after create_all.")


if __name__ == "__main__":
    debug_metadata()
