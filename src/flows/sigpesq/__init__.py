from src.flows.sigpesq.advisorships import ingest_advisorships_flow
from src.flows.sigpesq.all import ingest_sigpesq_flow
from src.flows.sigpesq.groups import ingest_research_groups_flow
from src.flows.sigpesq.projects import ingest_projects_flow

__all__ = [
    "ingest_advisorships_flow",
    "ingest_projects_flow",
    "ingest_research_groups_flow",
    "ingest_sigpesq_flow",
]
