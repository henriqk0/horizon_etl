import os
import sys

# Ensure the project root is in the path
sys.path.append(os.getcwd())

from loguru import logger
from research_domain import AdvisorshipController, FellowshipController


def cleanup():
    adv_ctrl = AdvisorshipController()
    fel_ctrl = FellowshipController()

    logger.info("Starting fellowship cleanup...")

    # 1. Map existing standard fellowships by name (uppercase)
    fels = fel_ctrl.get_all()
    fels_by_name = {}
    legacy_fels = {}
    for f in fels:
        name = getattr(f, "name", "").upper()
        f_id = getattr(f, "id", None)
        if name in ["VOLUNTÁRIO", "BOLSISTA"]:
            legacy_fels[f_id] = f
        else:
            fels_by_name[name] = f

    logger.info(f"Standard fellowships found: {list(fels_by_name.keys())}")
    logger.info(
        f"Legacy fellowships found: {[f'{f.name} (ID {f.id})' for f in legacy_fels.values()]}"
    )

    # 2. Re-link logic: For each legacy fellowship, find its proper replacement
    replacement_map = {}
    for lid, lfel in legacy_fels.items():
        desc = getattr(lfel, "description", "")
        if "Programa: " in desc:
            p_name = desc.split("Programa: ")[1].strip().upper()
            if p_name in fels_by_name:
                replacement_map[lid] = fels_by_name[p_name].id
                logger.info(
                    f"Mapping Legacy ID {lid} ('{lfel.name}') -> {p_name} (ID {fels_by_name[p_name].id})"
                )

    # 3. Update advisorships
    advs = adv_ctrl.get_all()
    updated_count = 0

    for a in advs:
        f_id = getattr(a, "fellowship_id", None)
        if f_id in replacement_map:
            a.fellowship_id = replacement_map[f_id]
            adv_ctrl.update(a)
            updated_count += 1

    logger.info(f"Updated {updated_count} advisorships with direct re-linking.")

    # 4. Delete orphaned legacy fellowships
    # Re-check counts
    advs = adv_ctrl.get_all()
    active_fel_ids = {getattr(a, "fellowship_id", None) for a in advs}

    for legacy_id in legacy_fels.keys():
        if legacy_id not in active_fel_ids:
            try:
                # Use SQL directly via session to avoid controller issues with objects
                session = fel_ctrl._service._repository._session
                # Fetch fresh object
                f = session.get(type(legacy_fels[legacy_id]), legacy_id)
                if f:
                    logger.info(
                        f"Deleting orphaned legacy fellowship: {f.name} (ID {legacy_id})"
                    )
                    session.delete(f)
                    session.commit()
            except Exception as e:
                logger.warning(f"Could not delete legacy fellowship {legacy_id}: {e}")
        else:
            logger.info(
                f"Legacy fellowship ID {legacy_id} still has active references. References: {list(active_fel_ids).count(legacy_id)}"
            )


if __name__ == "__main__":
    cleanup()
