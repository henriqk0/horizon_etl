from sqlalchemy import text

from src.core.logic.canonical_exporter import CanonicalDataExporter

SUPERVISOR_ROLE = "Supervisor"


def check_daniel_status():
    exporter = CanonicalDataExporter(sink=None)
    session = exporter.initiative_ctrl._service._repository._session

    # 1. Find Daniel's ID
    name = "Daniel Cruz Cavalieri"
    res = session.execute(
        text("SELECT id, name FROM persons WHERE LOWER(name) LIKE :n"),
        {"n": f"%{name.lower()}%"},
    ).fetchall()
    print("Potential Daniels found:")
    daniel_id = None
    for r in res:
        print(f"  ID: {r.id}, Name: {r.name}")
        if "Daniel Cruz Cavalieri" in r.name:
            daniel_id = r.id

    # 2. Check specific title
    title = "CLASSIFICAÇÃO DE NOTAS MUSICAIS UTILIZANDO A TRANSFORMADA WAVELET E REDES NEURAIS ARTIFICIAIS"
    print(f"\nChecking Title: {title}")

    query = text(
        """
        SELECT i.id, i.name, a.type, am.person_id AS supervisor_id
        FROM initiatives i
        LEFT JOIN advisorships a ON a.id = i.id
        LEFT JOIN advisorship_members am
            ON am.advisorship_id = a.id
           AND am.role_name = :supervisor_role
        WHERE LOWER(i.name) = LOWER(:t)
    """
    )
    row = session.execute(
        query,
        {"t": title, "supervisor_role": SUPERVISOR_ROLE},
    ).fetchone()

    if row:
        print(f"Found: ID={row.id}, Type={row.type}, SupervisorID={row.supervisor_id}")
        if row.supervisor_id == daniel_id:
            print("  -> Linked to Daniel correctly.")
        else:
            print(
                f"  -> Linked to Supervisor ID {row.supervisor_id} (Expected {daniel_id})"
            )
    else:
        print("NOT FOUND in DB.")


if __name__ == "__main__":
    check_daniel_status()
