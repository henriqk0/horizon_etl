from typing import Optional
from concurrent.futures import ThreadPoolExecutor
from itertools import islice

from dotenv import load_dotenv
from prefect import flow, get_run_logger, task
from research_domain import CampusController, ResearchGroupController

from src.adapters.sources.cnpq_crawler import CnpqCrawlerAdapter
from src.core.logic.strategies.cnpq_sync import CnpqSyncLogic
from src.notifications.telegram import telegram_flow_state_handlers
from src.tracking.recorder import tracking_recorder

load_dotenv()


@task
def get_groups_to_sync(
    limit: Optional[int] = None, offset: int = 0, campus_name: Optional[str] = None
):
    """
    Fetches research groups that have a CNPq URL, optionally filtering by campus name.
    """
    logger = get_run_logger()
    logger.info("Fetching research groups with CNPq URLs...")

    rg_ctrl = ResearchGroupController()
    all_groups = rg_ctrl.get_all()

    # Campus filtering if requested
    campus_id = None
    if campus_name:
        logger.info(f"Filtering by campus matching: '{campus_name}'")
        campus_ctrl = CampusController()
        campuses = campus_ctrl.get_all()
        matching_campuses = [
            c for c in campuses if campus_name.lower() in c.name.lower()
        ]

        if not matching_campuses:
            logger.warning(
                f"No campus found matching '{campus_name}'. Proceeding with no results."
            )
            return []

        if len(matching_campuses) > 1:
            logger.warning(
                f"Multiple campuses match '{campus_name}': {[c.name for c in matching_campuses]}. Using the first one: {matching_campuses[0].name}"
            )

        campus_id = matching_campuses[0].id
        logger.info(f"Using Campus ID {campus_id} for filtering.")

    sync_list = []
    for g in all_groups:
        if getattr(g, "cnpq_url", None):
            # Check campus filter
            if campus_id and getattr(g, "campus_id", None) != campus_id:
                continue

            sync_list.append({"id": g.id, "name": g.name, "url": g.cnpq_url})

    # Simple slicing for limit/offset
    if limit is not None:
        sync_list = sync_list[offset : offset + limit]
        logger.info(
            f"Batched {len(sync_list)} groups (offset={offset}, limit={limit})."
        )
    else:
        logger.info(f"Found {len(sync_list)} groups to synchronize.")

    return sync_list


@task
def download_cnpq_group_data(group_info: dict) -> dict:
    """
    Downloads CNPq data for a single research group (I/O-bound - can run in parallel).
    """
    logger = get_run_logger()
    url = group_info["url"]
    group_id = group_info["id"]
    group_name = group_info["name"]

    logger.info(f"Downloading CNPq data for: {group_name} ({url})")

    adapter = CnpqCrawlerAdapter()

    # 1. Extract data (I/O-bound - network request)
    data = adapter.get_group_data(url)
    if not data:
        logger.error(f"Failed to download data for {group_name}")
        return {
            "downloaded": False,
            "group_id": group_id,
            "group_name": group_name,
            "url": url,
            "data": None,
        }

    # 2. Extract parsed data (CPU-bound, but fast)
    members = adapter.extract_members(data)
    leaders = adapter.extract_leaders(data)
    lines = adapter.extract_research_lines(data)

    # Merge leaders into members
    if leaders:
        for leader_name in leaders:
            members.append(
                {
                    "name": leader_name,
                    "role": "Líder",
                    "data_inicio": None,
                    "data_fim": None,
                }
            )

    logger.info(
        f"Downloaded {group_name}: {len(members)} members, {len(lines)} lines"
    )

    return {
        "downloaded": True,
        "group_id": group_id,
        "group_name": group_name,
        "url": url,
        "data": data,
        "members": members,
        "lines": lines,
    }


@task
def process_cnpq_group_data(download_result: dict):
    """
    Processes downloaded CNPq data - writes to database (must run sequentially to avoid SQLite locks).
    """
    logger = get_run_logger()

    if not download_result.get("downloaded"):
        logger.error(f"Skipping processing for {download_result.get('group_name')} - download failed")
        return {
            "success": False,
            "group_id": download_result.get("group_id"),
            "group_name": download_result.get("group_name"),
            "url": download_result.get("url"),
        }

    group_id = download_result["group_id"]
    group_name = download_result["group_name"]
    url = download_result["url"]
    data = download_result["data"]
    members = download_result["members"]
    lines = download_result["lines"]

    logger.info(f"Processing CNPq data for: {group_name}")

    sync_logic = CnpqSyncLogic()

    # Record source record
    source_record = tracking_recorder.record_source_record(
        source_entity_type="cnpq_group_payload",
        payload=data,
        source_record_id=str(group_id),
        source_file=url,
        source_path=url,
    )

    # 1. Sync group info
    sync_logic.sync_group(
        group_id,
        data,
        source_record_id=getattr(source_record, "id", None),
    )

    # 2. Sync members
    from collections import Counter
    roles_count = Counter(m.get("role") for m in members)
    logger.info(f"Syncing {len(members)} members for {group_name}: {dict(roles_count)}")
    sync_logic.sync_members(group_id, members, source_file=url)

    # 3. Sync research lines (Knowledge Areas)
    logger.info(f"Syncing {len(lines)} research lines for {group_name}")
    sync_logic.sync_knowledge_areas(group_id, lines, source_file=url)

    return {
        "success": True,
        "group_id": group_id,
        "group_name": group_name,
        "url": url,
    }


@task
def sync_single_group(group_info: dict):
    """
    Synchronizes a single research group (DEPRECATED - use download_cnpq_group_data + process_cnpq_group_data for parallelization).
    """
    logger = get_run_logger()
    url = group_info["url"]
    group_id = group_info["id"]
    group_name = group_info["name"]

    logger.info(f"Synchronizing group: {group_name} ({url})")

    adapter = CnpqCrawlerAdapter()
    sync_logic = CnpqSyncLogic()

    # 1. Extract data
    data = adapter.get_group_data(url)
    if not data:
        logger.error(f"Failed to extract data for {group_name}")
        return {
            "success": False,
            "group_id": group_id,
            "group_name": group_name,
            "url": url,
        }
    source_record = tracking_recorder.record_source_record(
        source_entity_type="cnpq_group_payload",
        payload=data,
        source_record_id=str(group_id),
        source_file=url,
        source_path=url,
    )

    # 2. Sync group info
    sync_logic.sync_group(
        group_id,
        data,
        source_record_id=getattr(source_record, "id", None),
    )

    # 3. Extract and sync members
    members = adapter.extract_members(data)

    # 3.1 Extract and merge Leaders
    leaders = adapter.extract_leaders(data)
    if leaders:
        logger.info(f"Found {len(leaders)} leaders to sync.")
        for leader_name in leaders:
            members.append(
                {
                    "name": leader_name,
                    "role": "Líder",
                    "data_inicio": None,
                    "data_fim": None,
                }
            )

    from collections import Counter

    roles_count = Counter(m.get("role") for m in members)
    logger.info(
        f"Extracted {len(members)} members for {group_name}: {dict(roles_count)}"
    )
    sync_logic.sync_members(group_id, members, source_file=url)

    # 4. Extract and sync Research Lines (Knowledge Areas)
    lines = adapter.extract_research_lines(data)
    logger.info(f"Extracted {len(lines)} research lines for {group_name}")
    sync_logic.sync_knowledge_areas(group_id, lines, source_file=url)

    return {
        "success": True,
        "group_id": group_id,
        "group_name": group_name,
        "url": url,
    }


def build_cnpq_sync_summary(results: list[dict]) -> dict:
    failed_groups = [
        {
            "group_id": result.get("group_id"),
            "group_name": result.get("group_name"),
            "url": result.get("url"),
        }
        for result in results
        if not result.get("success")
    ]
    warnings = []
    if failed_groups:
        warnings.append(
            {
                "source": "cnpq",
                "severity": "warning",
                "code": "cnpq_group_sync_failed",
                "count": len(failed_groups),
                "examples": failed_groups[:5],
                "message": (
                    f"CNPq sync failed for {len(failed_groups)} group(s); "
                    "inspect URLs or portal availability."
                ),
            }
        )

    return {
        "source": "cnpq",
        "total_groups": len(results),
        "success_count": len(results) - len(failed_groups),
        "failed_count": len(failed_groups),
        "failed_groups": failed_groups,
        "warnings": warnings,
    }


def _chunks(iterable, size):
    """Yield successive chunks from iterable."""
    it = iter(iterable)
    while chunk := list(islice(it, size)):
        yield chunk


@flow(name="Sync CNPq Research Groups", **telegram_flow_state_handlers())
def sync_cnpq_groups_flow(campus_name: Optional[str] = None, max_parallel_downloads: int = 5):
    """
    Prefect flow to synchronize research groups with CNPq DGP mirror.

    Strategy:
    1. Parallel downloads of CNPq data in controlled batches (I/O-bound, network requests)
    2. Sequential processing/writes to DB (to avoid SQLite lock issues)

    Args:
        campus_name: Optional campus name to filter groups.
        max_parallel_downloads: Maximum number of concurrent downloads per batch.
    """
    logger = get_run_logger()
    logger.info(f"Starting CNPq Synchronization Flow (Filter: {campus_name or 'None'}, max_parallel={max_parallel_downloads})")

    groups = get_groups_to_sync(campus_name=campus_name)

    if not groups:
        logger.warning("No groups to synchronize.")
        return {"total_groups": 0, "success_count": 0, "failed_count": 0}

    BATCH_SIZE = max_parallel_downloads * 2  # Process in small batches to control memory

    all_results = []

    # Process in batches: parallel download + sequential DB write per batch
    group_chunks = list(_chunks(groups, BATCH_SIZE))
    total_batches = len(group_chunks)

    for batch_idx, group_chunk in enumerate(group_chunks, 1):
        logger.info(f"Processing batch {batch_idx}/{total_batches} ({len(group_chunk)} groups)...")

        # Step 1: Parallel download within batch
        logger.debug(f"Batch {batch_idx}: Downloading {len(group_chunk)} groups in parallel...")
        download_results = download_cnpq_group_data.map(group_chunk)

        # Step 2: Sequential processing within batch
        logger.debug(f"Batch {batch_idx}: Writing {len(group_chunk)} groups to DB (sequential)...")
        for download_result in download_results:
            result = process_cnpq_group_data(download_result)
            all_results.append(result)

        logger.info(f"Batch {batch_idx}/{total_batches} completed.")

    success_count = sum(1 for r in all_results if r.get("success"))
    summary = build_cnpq_sync_summary(all_results)
    logger.info(
        f"Flow finished. Successfully synchronized {success_count}/{len(groups)} groups."
    )
    return summary


if __name__ == "__main__":
    sync_cnpq_groups_flow()
