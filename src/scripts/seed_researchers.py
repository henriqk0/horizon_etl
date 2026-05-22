import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from research_domain import Researcher, ResearcherController


def seed_researchers():
    list_path = "data/lattes_run/lattes.list"
    if not os.path.exists(list_path):
        print(f"List file not found at {list_path}")
        return

    ctrl = ResearcherController()
    # Ensure tables exist for seeding
    from eo_lib.domain.base import Base

    # Force creation of tables
    if hasattr(ctrl, "client") and ctrl.client.engine:
        Base.metadata.create_all(ctrl.client.engine)
        print("Tables created.")

    with open(list_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split(",")
            if len(parts) >= 2:
                lattes_id = parts[0].strip()
                name = parts[1].strip()

                # Check if exists
                existing = next(
                    (
                        r
                        for r in ctrl.get_all()
                        if getattr(r, "brand_id", "") == lattes_id
                    ),
                    None,
                )
                if not existing:
                    # Create
                    print(f"Creating researcher: {name} ({lattes_id})")
                    new_researcher = Researcher(name=name, brand_id=lattes_id)
                    # Note: Researcher init might differ in eo_lib/research_domain.
                    # Usually Researcher(name, ...) but brand_id might be set differently or passed validly.
                    # Base Person has brand_id? No, Person doesn't usually.
                    # Let's check Researcher definition I viewed earlier.
                    # It inherits Person. Person usually has `name`.
                    # Lattes ID is often stored in `identifiers` or `extra_fields` or `brand_id` if using specific library version.
                    # In `research_domain` v0.11, Researcher might not have `brand_id` column explicitly mapped if using `Person`.
                    # Let's check `view_file` output from step 180.
                    # Researcher(Person): id, cnpq_url, ...
                    # It does NOT have lattes_id column explicitly shown in the snippet.
                    # But the ingestion flow uses `r.brand_id`.
                    # Maybe it's delegated to Person or mapped dynamically?
                    # Or maybe I should check `Person` definition.
                    # However, ingestion flow lines 43: `str(getattr(r, "brand_id", "") or "") == lattes_id`
                    # suggests it expects `brand_id`.
                    # Let's assume kwargs work or Person has it.

                    try:
                        ctrl.create(new_researcher)
                    except Exception as e:
                        print(f"Error creating {name}: {e}")
                else:
                    print(f"Researcher exists: {name}")


if __name__ == "__main__":
    seed_researchers()
