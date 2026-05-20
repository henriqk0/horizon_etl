
from eo_lib.infrastructure.database.postgres_client import PostgresClient
from sqlalchemy import text


def check_db():
    client = PostgresClient()
    session = client.get_session()

    # 1. Raw Count
    count = session.execute(text("SELECT count(*) FROM academic_educations WHERE researcher_id = 604")).scalar()
    print(f"Raw Count for 604: {count}")

    # 2. Exporter Query Logic (Replicating exactly what is in canonical_exporter.py)
    # Note: I'm using the query from the file as I remember it (with person join)
    query = text("""
                SELECT
                    ae.researcher_id,
                    org.name as institution,
                    et.name as degree,
                    ae.title as course_name,
                    ae.start_year,
                    ae.end_year,
                    ae.thesis_title,
                    p_adv.name as advisor_name
                FROM academic_educations ae
                LEFT JOIN organizations org ON ae.institution_id = org.id
                LEFT JOIN education_types et ON ae.education_type_id = et.id
                LEFT JOIN researchers adv ON ae.advisor_id = adv.id
                LEFT JOIN persons p_adv ON adv.id = p_adv.id
                WHERE ae.researcher_id = 604
    """)

    results = session.execute(query).fetchall()
    print(f"Exporter Query Count for 604: {len(results)}")
    for r in results:
        print(f" - {r}")

if __name__ == "__main__":
    check_db()
