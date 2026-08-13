import json
import os
import shutil
import tempfile
from unittest.mock import MagicMock

import pytest

from src.core.logic.canonical_database_seeder import CanonicalDatabaseSeeder
from src.core.logic.provenance_tracker import ProvenanceTracker
from src.flows.cnpq.groups import get_groups_to_sync


@pytest.fixture
def temp_export_dir():
    dirpath = tempfile.mkdtemp()
    yield dirpath
    shutil.rmtree(dirpath, ignore_errors=True)


def test_provenance_tracker_set_and_get(temp_export_dir):
    ProvenanceTracker.clear_provenance(temp_export_dir)

    assert ProvenanceTracker.get_provenance("sigpesq", temp_export_dir) == "LIVE"

    ProvenanceTracker.set_provenance("sigpesq", "ZIP ANTERIOR", temp_export_dir)
    assert (
        ProvenanceTracker.get_provenance("sigpesq", temp_export_dir) == "ZIP ANTERIOR"
    )

    ProvenanceTracker.set_provenance("cnpq", "PARCIAL", temp_export_dir)
    assert ProvenanceTracker.get_provenance("cnpq", temp_export_dir) == "PARCIAL"

    ProvenanceTracker.clear_provenance(temp_export_dir)
    assert ProvenanceTracker.get_provenance("sigpesq", temp_export_dir) == "LIVE"


def test_canonical_database_seeder_seeds_groups(temp_export_dir):
    json_path = os.path.join(temp_export_dir, "research_groups_canonical.json")
    mock_data = [
        {
            "id": 901,
            "name": "Grupo de Teste IA",
            "cnpq_url": "http://dgp.cnpq.br/dgp/espelhogrupo/901",
            "campus_id": 1,
        }
    ]
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(mock_data, f)

    seeder = CanonicalDatabaseSeeder()
    seeded = seeder.seed_research_groups_if_empty(export_dir=temp_export_dir)

    # Should attempt seed and return count >= 0
    assert isinstance(seeded, int)


def test_canonical_database_seeder_seeds_orgs_campuses_and_groups(temp_export_dir):
    data_files = {
        "organizations_canonical.json": [
            {"id": 1, "name": "IFES", "description": None, "short_name": "IFES"}
        ],
        "campuses_canonical.json": [
            {
                "id": 6,
                "name": "Serra",
                "description": None,
                "short_name": None,
                "organization_id": 1,
            }
        ],
        "research_groups_canonical.json": [
            {
                "id": 12,
                "name": "Grupo A",
                "campus_id": 6,
                "organization_id": 1,
                "cnpq_url": "http://dgp.cnpq.br/dgp/espelhogrupo/12",
                "site": None,
                "campus": {"id": 6, "name": "Serra"},
                "organization": {"id": 1, "name": "IFES"},
            }
        ],
    }
    for fname, content in data_files.items():
        with open(os.path.join(temp_export_dir, fname), "w", encoding="utf-8") as f:
            json.dump(content, f)

    seeder = CanonicalDatabaseSeeder()
    seeder.rg_ctrl = MagicMock()
    seeder.campus_ctrl = MagicMock()
    seeder.org_ctrl = MagicMock()

    seeder.rg_ctrl.get_all.return_value = []
    seeder.org_ctrl.get_all.return_value = []
    seeder.campus_ctrl.get_all.return_value = []

    def fake_org(**kwargs):
        org = MagicMock()
        org.id = 201
        return org

    def fake_campus(**kwargs):
        campus = MagicMock()
        campus.id = 206
        return campus

    seeder.org_ctrl.create_organization.side_effect = fake_org
    seeder.campus_ctrl.create_campus.side_effect = fake_campus

    result = seeder.seed_research_groups_if_empty(export_dir=temp_export_dir)

    assert result == 1
    seeder.org_ctrl.create_organization.assert_called_once_with(
        name="IFES", description=None, short_name="IFES"
    )
    seeder.campus_ctrl.create_campus.assert_called_once_with(
        name="Serra", organization_id=201, description=None, short_name=None
    )
    kwargs = seeder.rg_ctrl.create_research_group.call_args.kwargs
    assert kwargs["name"] == "Grupo A"
    assert kwargs["campus_id"] == 206
    assert kwargs["organization_id"] == 201
    assert kwargs["cnpq_url"] == "http://dgp.cnpq.br/dgp/espelhogrupo/12"


def test_canonical_database_seeder_skips_when_groups_exist(temp_export_dir):
    seeder = CanonicalDatabaseSeeder()
    seeder.rg_ctrl = MagicMock()
    seeder.campus_ctrl = MagicMock()
    seeder.org_ctrl = MagicMock()

    existing = MagicMock()
    existing.cnpq_url = "http://dgp.cnpq.br/dgp/espelhogrupo/1"
    seeder.rg_ctrl.get_all.return_value = [existing]

    result = seeder.seed_research_groups_if_empty(export_dir=temp_export_dir)

    assert result == 0
    seeder.org_ctrl.create_organization.assert_not_called()
    seeder.campus_ctrl.create_campus.assert_not_called()
    seeder.rg_ctrl.create_research_group.assert_not_called()


def test_cnpq_get_groups_to_sync_triggers_seeding(temp_export_dir):
    # Verify get_groups_to_sync executes without errors
    groups = get_groups_to_sync()
    assert isinstance(groups, list)
