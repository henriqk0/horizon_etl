import os  # noqa E402
import sys  # noqa E402

sys.path.append(os.getcwd())

from eo_lib.domain.base import Base
from eo_lib.infrastructure.database.postgres_client import PostgresClient

# Import all entities to ensure they are registered in metadata
# from eo_lib.domain.entities import *
# from research_domain.domain.entities import *


def recreate_db():
    print("Dropping all tables...")
    client = PostgresClient()
    engine = client._engine if hasattr(client, "_engine") else client.engine
    Base.metadata.drop_all(engine)
    print("Recreating all tables...")
    Base.metadata.create_all(engine)
    print("Database recreated successfully.")


if __name__ == "__main__":
    recreate_db()
