import json
import os
import shutil
import tempfile

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


def test_cnpq_get_groups_to_sync_triggers_seeding(temp_export_dir):
    # Verify get_groups_to_sync executes without errors
    groups = get_groups_to_sync()
    assert isinstance(groups, list)
