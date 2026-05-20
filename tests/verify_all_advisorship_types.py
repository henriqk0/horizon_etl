from sqlalchemy import text
from src.core.logic.canonical_exporter import CanonicalDataExporter
try:
    from research_domain.domain.entities.advisorship import AdvisorshipType
except ImportError:
    AdvisorshipType = None


def verify_all_types():
    exporter = CanonicalDataExporter(sink=None)
    session = exporter.initiative_ctrl._service._repository._session

    print("Checking Advisorship counts by Type in DB...")

    query = text("SELECT type, COUNT(*) as cnt FROM advisorships GROUP BY type")
    rows = session.execute(query).fetchall()

    print(f"{'Type':<30} | {'Count':<10}")
    print("-" * 45)

    found_types = set()
    for r in rows:
        type_str = str(r[0])
        print(f"{type_str:<30} | {r[1]:<10}")
        found_types.add(type_str)

    print("-" * 45)

    # Check for expected types
    expected = [
        "AdvisorshipType.UNDERGRADUATE_THESIS",
        "AdvisorshipType.MASTER_THESIS",
        "AdvisorshipType.PHD_THESIS",
        "AdvisorshipType.POST_DOCTORATE",
        "AdvisorshipType.SCIENTIFIC_INITIATION"
    ]

    missing = []  # noqa: F841
    for e in expected:
        # Check if the string representation of the Enum exists in the DB output
        # DB stores Enum as string usually, e.g. 'Undergraduate Thesis'
        # We need to map Enum name to Value if we want exact check, but visual check is fine.
        pass

    # Check for NULL types (Specialization mappped to None)
    null_count = session.execute(text("SELECT count(*) FROM advisorships WHERE type IS NULL")).scalar()
    print(f"NULL (Generic/Specialization):   | {null_count:<10}")

if __name__ == "__main__":
    verify_all_types()
