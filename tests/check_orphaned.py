from sqlalchemy import text
from src.core.logic.canonical_exporter import CanonicalDataExporter


def check_orphaned_initiatives():
    exporter = CanonicalDataExporter(sink=None)
    session = exporter.initiative_ctrl._service._repository._session

    # Title known to have failed:
    title = 'Desenvolvimento de Materiais Didáticos Inovadores Para o Ensino de Disciplinas Técnicas com Tecnologias da Indústria 4.0'

    print(f"Checking Title: {title}")

    # Check in Initiatives
    query_init = text("SELECT id, name, initiative_type_id FROM initiatives WHERE LOWER(name) = LOWER(:t)")
    init = session.execute(query_init, {"t": title}).fetchone()

    if init:
        db_name = init.name
        print(f"DB Name: '{db_name}'")
        print(f"Input  : '{title}'")
        print(f"DB Hex : {db_name.encode('utf-8').hex()}")
        print(f"In Hex : {title.encode('utf-8').hex()}")

        # Test SQLite LOWER
        test_val = "Detecção"
        res = session.execute(text(f"SELECT LOWER('{test_val}')")).scalar()
        print(f"SQLite LOWER('{test_val}') = '{res}'")

        # Check match in Python
        print(f"Python Match (lower): {db_name.lower() == title.lower()}")

        # Check specific query failure
        chk_sql = text("SELECT id FROM initiatives WHERE LOWER(name) = LOWER(:t)")
        found = session.execute(chk_sql, {"t": title}).fetchone()
        print(f"Query found with LOWER match? {found}")
        print(f"Found in INITIATIVES: ID={init.id}, TypeID={init.initiative_type_id}")

        # Check in Advisorships
        query_adv = text("SELECT id, type FROM advisorships WHERE id = :id")
        adv = session.execute(query_adv, {"id": init.id}).fetchone()

        if adv:
            print(f"Found in ADVISORSHIPS: Type={adv.type}")
        else:
             print("NOT found in ADVISORSHIPS table! (Orphaned Initiative / Wrong Class)")

    else:
        print("NOT found in INITIATIVES table (Strange, considering Unique Constraint error)")

if __name__ == "__main__":
    check_orphaned_initiatives()
