from src.flows.sigpesq.advisorships import ingest_advisorships_flow, persist_advisorships
from src.flows.sigpesq.all import ingest_sigpesq_flow, ingest_sigpesq_parallel_flow
from src.flows.sigpesq.groups import (
    download_sigpesq_category,
    ingest_projects_flow,
    ingest_research_groups_flow,
    persist_projects,
    persist_research_groups,
)

__all__ = [
    "download_sigpesq_category",
    "ingest_advisorships_flow",
    "ingest_projects_flow",
    "ingest_research_groups_flow",
    "ingest_sigpesq_flow",
    "ingest_sigpesq_parallel_flow",
    "persist_advisorships",
    "persist_projects",
    "persist_research_groups",
]