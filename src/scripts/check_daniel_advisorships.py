
import sqlite3
import os

SUPERVISOR_ROLE = "Supervisor"


def check_daniel():
    db_path = "/home/paulossjunior/projects/horizon_project/horizon_etl/db/horizon.db"
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 1. Find Daniel
    cursor.execute("SELECT id, name FROM persons WHERE name LIKE '%Daniel Cruz Cavalieri%'")
    results = cursor.fetchall()

    if not results:
        print("Daniel Cruz Cavalieri not found in persons table.")
        # Try finding by short name or parts
        cursor.execute("SELECT id, name FROM persons WHERE name LIKE '%Cavalieri%'")
        results = cursor.fetchall()
        if not results:
             print("No one with 'Cavalieri' found either.")
             return

    for row in results:
        person_id, name = row
        print(f"Found person: ID={person_id}, Name={name}")

        # 2. Check advisorships for this person as supervisor
        cursor.execute("""
            SELECT a.id, i.name, a.type, i.status
            FROM advisorships a
            JOIN initiatives i ON a.id = i.id
            JOIN advisorship_members am ON am.advisorship_id = a.id
            WHERE am.person_id = ? AND am.role_name = ?
        """, (person_id, SUPERVISOR_ROLE))
        advisorships = cursor.fetchall()
        print(f"Advisorships as supervisor for {name} (ID {person_id}): {len(advisorships)}")
        for adv in advisorships:
            print(f" - ID={adv[0]}, Title={adv[1]}, Type={adv[2]}, Status={adv[3]}")

        # 3. Check team links
        cursor.execute("""
            SELECT im.initiative_id, i.name, im.role
            FROM initiative_members im
            JOIN initiatives i ON im.initiative_id = i.id
            WHERE im.person_id = ?
        """, (person_id,))
        team_links = cursor.fetchall()
        print(f"Team links for {name} (ID {person_id}): {len(team_links)}")
        for link in team_links:
            print(f" - Initiative ID={link[0]}, Title={link[1]}, Role={link[2]}")

    conn.close()

if __name__ == "__main__":
    check_daniel()
