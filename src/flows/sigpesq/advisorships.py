import glob
import os

import pandas as pd
from dotenv import load_dotenv
from prefect import flow, get_run_logger, task

from src.adapters.sources.sigpesq.adapter import SigPesqAdapter
from src.core.logic.initiative_identity import normalize_sigpesq_code
from src.core.logic.project_loader import ProjectLoader
from src.core.logic.strategies.sigpesq_advisorships import (
    SigPesqAdvisorshipMappingStrategy,
)
from src.notifications.telegram import telegram_flow_state_handlers

load_dotenv()


@task
def persist_advisorships():
    """
    Finds the latest Advisorships Excel file and loads it into the database.
    """
    logger = get_run_logger()

    # SigPesqAdapter typically downloads to data/raw/sigpesq/
    # The AdvisorshipsDownloadStrategy might save to a specific subfolder.
    # Looking at SigPesqFileLoader.load_files logic would help,
    # but we follow the pattern in ingest_sigpesq_projects.py

    files = glob.glob("data/raw/sigpesq/advisorships/**/*.xlsx", recursive=True)
    if not files:
        # Try generic sigpesq folder if specific one doesn't exist
        files = glob.glob("data/raw/sigpesq/*.xlsx")

    if not files:
        logger.warning("No Advisorship Excel files found.")
        return

    # Sort by year directory in ascending order (oldest first)
    # so the most recent year's values take precedence (last processed wins).
    files.sort(key=lambda f: os.path.basename(os.path.dirname(f)))

    loader = ProjectLoader(mapping_strategy=SigPesqAdvisorshipMappingStrategy())

    # Ensure "Advisorship" initiative type exists once
    existing_types = loader.controller.list_initiative_types()
    raw_type = next(
        (
            t
            for t in existing_types
            if (t.get("name") if isinstance(t, dict) else getattr(t, "name", ""))
            == "Advisorship"
        ),
        None,
    )

    if not raw_type:
        logger.info("Creating 'Advisorship' initiative type...")
        raw_type = loader.controller.create_initiative_type(
            name="Advisorship", description="Bolsas e Orientações importadas do SigPesq"
        )

    # Wrap in object if it's a dict (ProjectLoader expects .id)
    if isinstance(raw_type, dict):

        class Obj:
            pass

        loader.initiative_type = Obj()
        loader.initiative_type.id = raw_type.get("id")
        loader.initiative_type.name = raw_type.get("name")
    else:
        loader.initiative_type = raw_type

    for file_path in files:
        logger.info(f"Loading Advisorships from {file_path}")
        df = pd.read_excel(file_path)
        df = df.fillna("")

        # Within-file dedup: keep only the row with the highest Id per CodPT.
        # This prevents multiple phases of the same workplan from clobbering each other.
        if "CodPT" in df.columns and "Id" in df.columns:
            before = len(df)
            df["_norm_codpt"] = df["CodPT"].apply(
                lambda x: normalize_sigpesq_code(x) if pd.notna(x) else ""
            )
            df = df.sort_values("Id", ascending=False)
            valid = df["_norm_codpt"].str.len() > 0
            df = pd.concat(
                [
                    df[valid].drop_duplicates(subset=["_norm_codpt"], keep="first"),
                    df[~valid],
                ]
            )
            df = df.drop(columns=["_norm_codpt"])
            after = len(df)
            if after < before:
                logger.info(
                    f"  Deduped {before - after} rows by CodPT (kept highest Id per workplan)"
                )

        records = df.to_dict("records")
        loader.process_records(records, source_file=file_path)

    # Final pass: Recalculate parent project dates and status from DB
    loader.recalculate_all_parent_statuses()


@flow(name="Ingest SigPesq Advisorships", **telegram_flow_state_handlers())
def ingest_advisorships_flow() -> None:
    """
    Prefect flow for ingesting Advisorships (Bolsistas) from SigPesq.
    """
    logger = get_run_logger()
    logger.info("Initializing SigPesq Advisorships Ingestion Flow")

    from agent_sigpesq.strategies import AdvisorshipsDownloadStrategy

    adapter = SigPesqAdapter()

    # 1. Extract Advisorships
    logger.info("Extracting Advisorships...")
    adapter.extract(download_strategies=[AdvisorshipsDownloadStrategy()])

    # 2. Persist Advisorships
    persist_advisorships()

    logger.info("Advisorships Ingestion finished successfully.")


if __name__ == "__main__":
    ingest_advisorships_flow()
