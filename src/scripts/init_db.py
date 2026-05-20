import sys
import os

sys.path.append(os.getcwd())

from eo_lib.infrastructure.database.postgres_client import PostgresClient
from eo_lib.domain.base import Base

# Import all entities to ensure they are registered in metadata
from eo_lib.domain.entities import *
from research_domain.domain.entities import *


def init_db():
    print("Initializing database...")
    client = PostgresClient()
    # Use _engine as suggested by error, or try get_engine if exists.
    # Error said "Did you mean: '_engine'?" so let's try that.
    engine = client._engine if hasattr(client, '_engine') else client.engine
    Base.metadata.create_all(engine)
    print("Database initialized.")

if __name__ == "__main__":
    init_db()
