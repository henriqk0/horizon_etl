import sqlite3
from pathlib import Path

from src.core.logic.person_consolidator import PersonConsolidator

SCHEMA_SQL = """
CREATE TABLE persons (
    id INTEGER PRIMARY KEY,
    name VARCHAR NOT NULL,
    identification_id VARCHAR,
    birthday DATE
);
CREATE TABLE researchers (
    id INTEGER PRIMARY KEY,
    cnpq_url VARCHAR(255),
    google_scholar_url VARCHAR(255),
    resume VARCHAR,
    citation_names VARCHAR(500)
);
CREATE TABLE person_emails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL,
    email VARCHAR NOT NULL
);
CREATE TABLE advisorships (
    id INTEGER PRIMARY KEY,
    fellowship_id INTEGER,
    institution_id INTEGER
);
CREATE TABLE advisorship_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    advisorship_id INTEGER NOT NULL,
    person_id INTEGER NOT NULL,
    role_id INTEGER,
    role_name VARCHAR(50),
    start_date DATETIME,
    end_date DATETIME
);
CREATE TABLE academic_educations (
    id INTEGER PRIMARY KEY,
    researcher_id INTEGER NOT NULL,
    education_type_id INTEGER NOT NULL,
    title VARCHAR(255) NOT NULL,
    start_year INTEGER NOT NULL,
    end_year INTEGER,
    thesis_title VARCHAR(500),
    institution_id INTEGER NOT NULL,
    advisor_id INTEGER,
    co_advisor_id INTEGER
);
CREATE TABLE article_authors (
    article_id INTEGER NOT NULL,
    researcher_id INTEGER NOT NULL,
    PRIMARY KEY (article_id, researcher_id)
);
CREATE TABLE researcher_knowledge_areas (
    researcher_id INTEGER NOT NULL,
    area_id INTEGER NOT NULL,
    PRIMARY KEY (researcher_id, area_id)
);
CREATE TABLE initiative_persons (
    initiative_id INTEGER NOT NULL,
    person_id INTEGER NOT NULL,
    PRIMARY KEY (initiative_id, person_id)
);
CREATE TABLE organization_persons (
    organization_id INTEGER NOT NULL,
    person_id INTEGER NOT NULL,
    PRIMARY KEY (organization_id, person_id)
);
CREATE TABLE team_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL,
    team_id INTEGER NOT NULL,
    role_id INTEGER,
    start_date DATETIME,
    end_date DATETIME
);
"""


def test_consolidate_pair_moves_links_and_removes_loser(tmp_path: Path):
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_SQL)

    conn.execute(
        "INSERT INTO persons (id, name, identification_id) VALUES (2981, 'Paulo Sergio dos Santos Junior', '8400407353673370')"
    )
    conn.execute(
        "INSERT INTO persons (id, name, identification_id) VALUES (452, 'Paulo Sérgio Dos Santos Júnior', NULL)"
    )
    conn.execute(
        "INSERT INTO researchers (id, cnpq_url, resume) VALUES (2981, 'http://lattes.cnpq.br/8400407353673370', 'resume ok')"
    )
    conn.execute("INSERT INTO researchers (id) VALUES (452)")
    conn.execute(
        "INSERT INTO person_emails (person_id, email) VALUES (452, 'paulo@example.com')"
    )
    conn.execute("INSERT INTO advisorships (id) VALUES (1)")
    conn.execute(
        "INSERT INTO advisorship_members (advisorship_id, person_id, role_name) VALUES (1, 452, 'Supervisor')"
    )
    conn.execute(
        "INSERT INTO academic_educations (id, researcher_id, education_type_id, title, start_year, institution_id) VALUES (1, 452, 1, 'Mestrado', 2007, 1)"
    )
    conn.execute(
        "INSERT INTO article_authors (article_id, researcher_id) VALUES (10, 452)"
    )
    conn.execute(
        "INSERT INTO researcher_knowledge_areas (researcher_id, area_id) VALUES (452, 99)"
    )
    conn.execute(
        "INSERT INTO initiative_persons (initiative_id, person_id) VALUES (77, 452)"
    )
    conn.execute(
        "INSERT INTO organization_persons (organization_id, person_id) VALUES (88, 452)"
    )
    conn.execute(
        "INSERT INTO team_members (person_id, team_id, role_id) VALUES (452, 55, 2)"
    )
    conn.commit()
    conn.close()

    consolidator = PersonConsolidator(str(db_path))
    consolidator.consolidate_pair(2981, 452)

    check = sqlite3.connect(db_path)
    cur = check.cursor()
    assert cur.execute("SELECT COUNT(*) FROM persons WHERE id = 452").fetchone()[0] == 0
    assert (
        cur.execute("SELECT COUNT(*) FROM researchers WHERE id = 452").fetchone()[0]
        == 0
    )
    assert (
        cur.execute(
            "SELECT person_id FROM advisorship_members WHERE advisorship_id = 1 AND role_name = 'Supervisor'"
        ).fetchone()[0]
        == 2981
    )
    assert (
        cur.execute(
            "SELECT researcher_id FROM academic_educations WHERE id = 1"
        ).fetchone()[0]
        == 2981
    )
    assert (
        cur.execute(
            "SELECT researcher_id FROM article_authors WHERE article_id = 10"
        ).fetchone()[0]
        == 2981
    )
    assert (
        cur.execute(
            "SELECT researcher_id FROM researcher_knowledge_areas WHERE area_id = 99"
        ).fetchone()[0]
        == 2981
    )
    assert (
        cur.execute(
            "SELECT person_id FROM initiative_persons WHERE initiative_id = 77"
        ).fetchone()[0]
        == 2981
    )
    assert (
        cur.execute(
            "SELECT person_id FROM organization_persons WHERE organization_id = 88"
        ).fetchone()[0]
        == 2981
    )
    assert (
        cur.execute("SELECT person_id FROM team_members WHERE team_id = 55").fetchone()[
            0
        ]
        == 2981
    )
    assert (
        cur.execute(
            "SELECT person_id FROM person_emails WHERE email = 'paulo@example.com'"
        ).fetchone()[0]
        == 2981
    )


def test_consolidate_all_merges_detected_duplicate_groups(tmp_path: Path):
    db_path = tmp_path / "test_all.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_SQL)
    conn.execute(
        "INSERT INTO persons (id, name, identification_id) VALUES (1, 'Gustavo Maia De Almeida', 'gustavo@ifes.edu.br')"
    )
    conn.execute(
        "INSERT INTO persons (id, name, identification_id) VALUES (2, 'Gustavo Maia de Almeida', 'Gustavo Maia de Almeida')"
    )
    conn.execute("INSERT INTO researchers (id, resume) VALUES (1, 'resume')")
    conn.execute("INSERT INTO researchers (id) VALUES (2)")
    conn.commit()
    conn.close()

    merged = PersonConsolidator(str(db_path)).consolidate_all()

    check = sqlite3.connect(db_path)
    cur = check.cursor()
    assert merged == 1
    assert cur.execute("SELECT COUNT(*) FROM persons").fetchone()[0] == 1
    assert cur.execute("SELECT id FROM persons").fetchone()[0] == 1


def test_find_duplicate_groups_prefers_real_identifier_over_name_identifier(
    tmp_path: Path,
):
    db_path = tmp_path / "quality.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_SQL)
    conn.execute(
        "INSERT INTO persons (id, name, identification_id) VALUES (1, 'Carlos Roberto Pires Campos', 'carlosr@ifes.edu.br')"
    )
    conn.execute(
        "INSERT INTO persons (id, name, identification_id) VALUES (2, 'Carlos Roberto Pires Campos', 'Carlos Roberto Pires Campos')"
    )
    conn.execute(
        "INSERT INTO person_emails (person_id, email) VALUES (1, 'carlosr@ifes.edu.br')"
    )
    conn.commit()
    conn.close()

    groups = PersonConsolidator(str(db_path)).find_duplicate_groups()

    assert len(groups) == 1
    assert groups[0].winner_id == 1
    assert groups[0].loser_ids == [2]


def test_consolidate_pair_transfers_identification_id_without_unique_conflict(
    tmp_path: Path,
):
    db_path = tmp_path / "unique_id.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_SQL)
    conn.execute(
        "CREATE UNIQUE INDEX uq_person_identification_id ON persons(identification_id)"
    )
    conn.execute(
        "INSERT INTO persons (id, name, identification_id) VALUES (1, 'Pessoa A', NULL)"
    )
    conn.execute(
        "INSERT INTO persons (id, name, identification_id) VALUES (2, 'Pessoa A', 'pessoa@ifes.edu.br')"
    )
    conn.commit()
    conn.close()

    PersonConsolidator(str(db_path)).consolidate_pair(1, 2)

    check = sqlite3.connect(db_path)
    cur = check.cursor()
    assert (
        cur.execute("SELECT identification_id FROM persons WHERE id = 1").fetchone()[0]
        == "pessoa@ifes.edu.br"
    )
    assert cur.execute("SELECT COUNT(*) FROM persons WHERE id = 2").fetchone()[0] == 0


def test_consolidate_pair_reassigns_email_without_unique_conflict(tmp_path: Path):
    db_path = tmp_path / "unique_email.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_SQL)
    conn.execute(
        "CREATE UNIQUE INDEX ux_person_emails_lower_email ON person_emails(lower(email))"
    )
    conn.execute("INSERT INTO persons (id, name) VALUES (1, 'Pessoa A')")
    conn.execute("INSERT INTO persons (id, name) VALUES (2, 'Pessoa A')")
    conn.execute(
        "INSERT INTO person_emails (person_id, email) VALUES (2, 'pessoa@ifes.edu.br')"
    )
    conn.commit()
    conn.close()

    PersonConsolidator(str(db_path)).consolidate_pair(1, 2)

    check = sqlite3.connect(db_path)
    cur = check.cursor()
    assert (
        cur.execute(
            "SELECT person_id FROM person_emails WHERE lower(email) = lower('pessoa@ifes.edu.br')"
        ).fetchone()[0]
        == 1
    )
    assert cur.execute("SELECT COUNT(*) FROM persons WHERE id = 2").fetchone()[0] == 0
