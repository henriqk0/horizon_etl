from datetime import datetime
from unittest.mock import MagicMock

from src.core.logic.canonical_exporter import CanonicalDataExporter


class _FakeRow:
    """Minimal stand-in for a SQLAlchemy Row exposing ``._mapping``."""

    def __init__(self, data):
        self._mapping = data


def _make_row(**overrides):
    base = {
        "id": 1001,
        "name": "Projeto A",
        "status": "Active",
        "description": "desc",
        "start_date": datetime(2022, 1, 1),
        "end_date": datetime(2023, 12, 31),
        "advisorship_type": "Scientific Initiation",
        "initiative_type_name": "Advisorship",
        "student_id": 700,
        "person_id": 700,
        "person_name": "Student One",
        "supervisor_id": 701,
        "supervisor_name": "Supervisor One",
        "parent_id": 500,
        "parent_name": "Projeto A",
        "parent_status": "Active",
        "parent_description": "parent desc",
        "parent_start_date": datetime(2020, 1, 1),
        "parent_end_date": datetime(2024, 12, 31),
        "fellowship_id": None,
        "fellowship_name": None,
        "fellowship_description": None,
        "fellowship_value": None,
        "sponsor_name": None,
    }
    base.update(overrides)
    return _FakeRow(base)


def _make_exporter():
    exporter = CanonicalDataExporter.__new__(CanonicalDataExporter)
    exporter.sink = MagicMock()
    resolver = MagicMock()
    resolver.get_campus.return_value = {"id": 1, "name": "Alegre"}
    exporter._campus_resolver = resolver
    exporter.initiative_ctrl = MagicMock()
    exporter._fetch_advisorship_export_rows = MagicMock()
    return exporter


def test_export_advisorships_groups_by_parent_and_carries_contract_keys():
    exporter = _make_exporter()
    exporter._fetch_advisorship_export_rows.return_value = [
        _make_row(),
        _make_row(
            id=1002,
            name="Orientação B",
            student_id=800,
            person_id=800,
            person_name="Student Two",
            parent_id=None,
            parent_name=None,
        ),
    ]

    exporter.export_advisorships("data/exports/advisorships_canonical.json")

    exported = exporter.sink.export.call_args[0][0]

    assert exported[0]["id"] == 500
    assert exported[0]["name"] == "Projeto A"
    assert len(exported[0]["advisorships"]) == 1

    adv = exported[0]["advisorships"][0]
    assert adv["student_id"] == 700
    assert adv["student_name"] == "Student One"
    assert adv["parent_id"] == 500
    assert adv["supervisor_id"] == 701
    assert adv["supervisor_name"] == "Supervisor One"
    assert adv["person_id"] == 700
    assert adv["person_name"] == "Student One"

    orphan_bucket = exported[1]
    assert orphan_bucket["name"] == "Sem Projeto Associado"
    assert len(orphan_bucket["advisorships"]) == 1
    assert orphan_bucket["advisorships"][0]["id"] == 1002
    assert orphan_bucket["advisorships"][0]["student_name"] == "Student Two"


def test_export_advisorships_fellowship_contract_key():
    exporter = _make_exporter()
    exporter._fetch_advisorship_export_rows.return_value = [
        _make_row(
            fellowship_id=9,
            fellowship_name="PIBIC",
            fellowship_description="desc",
            fellowship_value=800.0,
            sponsor_name="CNPq",
        )
    ]

    exporter.export_advisorships("data/exports/advisorships_canonical.json")

    adv = exporter.sink.export.call_args[0][0][0]["advisorships"][0]
    assert adv["fellowship"] == {
        "id": 9,
        "name": "PIBIC",
        "description": "desc",
        "value": 800.0,
        "sponsor_name": "CNPq",
    }
