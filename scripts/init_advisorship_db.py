import os

from eo_lib.infrastructure.database.postgres_client import PostgresClient
from research_domain.domain.entities import Advisorship, Fellowship


def init_missing_tables():
    client = PostgresClient()
    engine = client.get_engine()

    from eo_lib.domain.entities import Initiative
    from research_domain.domain.entities import (
        Campus,
        KnowledgeArea,
        Researcher,
        ResearchGroup,
        University,
    )

    # Use the declarative base common to all entities
    # It's usually accessible via any of the entities' metadata
    Advisorship.metadata.create_all(engine)
    print("Database tables initialized (including Advisorships and Fellowships).")


if __name__ == "__main__":
    init_missing_tables()
