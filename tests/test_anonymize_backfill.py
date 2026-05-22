import sqlite3

from src.core.logic.pii_anonymizer import is_anonymized_cpf, is_anonymized_email
from src.flows.maintenance.anonymize_backfill import (
    _anonymize_table_column,
    _discover_pii_columns,
    audit_pii,
)


def _make_conn(sql: str) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(sql)
    return conn


# --- _discover_pii_columns ---


def test_discover_pii_columns_finds_identification_id():
    conn = _make_conn(
        "CREATE TABLE persons (id INTEGER PRIMARY KEY, name TEXT, identification_id TEXT);"
    )
    cols = _discover_pii_columns(conn)
    assert any(
        c["table"] == "persons" and c["column"] == "identification_id" for c in cols
    )


def test_discover_pii_columns_finds_email():
    conn = _make_conn(
        "CREATE TABLE person_emails (id INTEGER PRIMARY KEY, person_id INTEGER, email TEXT);"
    )
    cols = _discover_pii_columns(conn)
    assert any(c["table"] == "person_emails" and c["column"] == "email" for c in cols)


def test_discover_pii_columns_ignores_non_pii():
    conn = _make_conn(
        "CREATE TABLE persons (id INTEGER PRIMARY KEY, name TEXT, campus TEXT);"
    )
    cols = _discover_pii_columns(conn)
    assert cols == []


def test_discover_pii_columns_multiple_tables():
    conn = _make_conn(
        """
        CREATE TABLE persons (id INTEGER PRIMARY KEY, identification_id TEXT);
        CREATE TABLE person_emails (id INTEGER PRIMARY KEY, email TEXT);
    """
    )
    cols = _discover_pii_columns(conn)
    assert len(cols) == 2


# --- _anonymize_table_column ---


def test_anonymize_table_column_anonymizes_cpf():
    conn = _make_conn(
        """
        CREATE TABLE persons (id INTEGER PRIMARY KEY, identification_id TEXT);
        INSERT INTO persons VALUES (1, '12345678901');
    """
    )
    stats = _anonymize_table_column(conn, "persons", "identification_id", "cpf")
    row = conn.execute("SELECT identification_id FROM persons WHERE id=1").fetchone()[0]
    assert is_anonymized_cpf(row)
    assert stats["anonymized"] == 1
    assert stats["errors"] == 0


def test_anonymize_table_column_anonymizes_email():
    conn = _make_conn(
        """
        CREATE TABLE person_emails (id INTEGER PRIMARY KEY, email TEXT);
        INSERT INTO person_emails VALUES (1, 'user@example.com');
    """
    )
    stats = _anonymize_table_column(conn, "person_emails", "email", "email")
    row = conn.execute("SELECT email FROM person_emails WHERE id=1").fetchone()[0]
    assert is_anonymized_email(row)
    assert stats["anonymized"] == 1


def test_anonymize_table_column_skips_null():
    conn = _make_conn(
        """
        CREATE TABLE persons (id INTEGER PRIMARY KEY, identification_id TEXT);
        INSERT INTO persons VALUES (1, NULL);
    """
    )
    stats = _anonymize_table_column(conn, "persons", "identification_id", "cpf")
    assert stats["skipped_null"] == 1
    assert stats["anonymized"] == 0


def test_anonymize_table_column_idempotent_already_anonymized_cpf():
    conn = _make_conn(
        """
        CREATE TABLE persons (id INTEGER PRIMARY KEY, identification_id TEXT);
        INSERT INTO persons VALUES (1, 'LGPD-abc1234567890123');
    """
    )
    stats = _anonymize_table_column(conn, "persons", "identification_id", "cpf")
    assert stats["already_anonymized"] == 1
    assert stats["anonymized"] == 0


def test_anonymize_table_column_idempotent_already_anonymized_email():
    conn = _make_conn(
        """
        CREATE TABLE person_emails (id INTEGER PRIMARY KEY, email TEXT);
        INSERT INTO person_emails VALUES (1, 'abc123456789@anon.lgpd');
    """
    )
    stats = _anonymize_table_column(conn, "person_emails", "email", "email")
    assert stats["already_anonymized"] == 1
    assert stats["anonymized"] == 0


def test_anonymize_table_column_second_run_is_noop():
    conn = _make_conn(
        """
        CREATE TABLE persons (id INTEGER PRIMARY KEY, identification_id TEXT);
        INSERT INTO persons VALUES (1, '12345678901');
        INSERT INTO persons VALUES (2, '98765432100');
    """
    )
    _anonymize_table_column(conn, "persons", "identification_id", "cpf")
    stats2 = _anonymize_table_column(conn, "persons", "identification_id", "cpf")
    assert stats2["anonymized"] == 0
    assert stats2["already_anonymized"] == 2


def test_anonymize_table_column_stats_correct():
    conn = _make_conn(
        """
        CREATE TABLE persons (id INTEGER PRIMARY KEY, identification_id TEXT);
        INSERT INTO persons VALUES (1, '12345678901');
        INSERT INTO persons VALUES (2, NULL);
        INSERT INTO persons VALUES (3, 'LGPD-existinghash12345');
    """
    )
    stats = _anonymize_table_column(conn, "persons", "identification_id", "cpf")
    assert stats["total_rows"] == 3
    assert stats["anonymized"] == 1
    assert stats["skipped_null"] == 1
    assert stats["already_anonymized"] == 1
    assert stats["errors"] == 0


# --- audit_pii ---


def test_audit_pii_runs_without_error(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE persons (id INTEGER PRIMARY KEY, identification_id TEXT, name TEXT)"
    )
    conn.execute("INSERT INTO persons VALUES (1, 'LGPD-abc1234567890123', 'Alice')")
    conn.commit()
    conn.close()
    audit_pii(db_path=db_path)


def test_audit_pii_empty_db(tmp_path):
    db_path = str(tmp_path / "empty.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE other (id INTEGER PRIMARY KEY, foo TEXT)")
    conn.commit()
    conn.close()
    audit_pii(db_path=db_path)
