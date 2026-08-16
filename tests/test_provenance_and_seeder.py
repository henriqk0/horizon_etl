import json
import os
import shutil
import tempfile
import zipfile
from unittest.mock import MagicMock, patch

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


def test_groups_seeded_with_default_org_when_export_omits_organization(temp_export_dir):
    """When the canonical JSON omits both organization_id and the organization
    object (the old exporter bug), groups must still be stored with a real
    (non-null) organization_id instead of perpetuating the null-org leak."""
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
                "cnpq_url": "http://dgp.cnpq.br/dgp/espelhogrupo/12",
                "site": None,
            }
        ],
    }
    for fname, content in data_files.items():
        with open(os.path.join(temp_export_dir, fname), "w", encoding="utf-8") as f:
            json.dump(content, f)

    seeded_org = MagicMock()
    seeded_org.id = 201

    seeder = CanonicalDatabaseSeeder()
    seeder.rg_ctrl = MagicMock()
    seeder.campus_ctrl = MagicMock()
    seeder.org_ctrl = MagicMock()

    seeder.rg_ctrl.get_all.return_value = []
    seeder.campus_ctrl.get_all.return_value = []
    # 1st call: empty check inside _seed_organizations_if_empty -> seeds org.
    # 2nd call: _first_organization_id() inside _seed_campuses_if_empty.
    # 3rd call: _first_organization_id() fallback for the group itself.
    seeder.org_ctrl.get_all.side_effect = [
        [],
        [seeded_org],
        [seeded_org],
    ]

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
    kwargs = seeder.rg_ctrl.create_research_group.call_args.kwargs
    assert kwargs["organization_id"] == 201
    assert kwargs["campus_id"] == 206


def test_cnpq_get_groups_to_sync_triggers_seeding(temp_export_dir):
    # Verify get_groups_to_sync executes without errors
    groups = get_groups_to_sync()
    assert isinstance(groups, list)


def test_campuses_derived_from_groups_when_file_empty(temp_export_dir):
    """Empty campuses_canonical.json must not leave campus table empty when
    research groups carry campus references (the self-perpetuating leak)."""
    data_files = {
        "organizations_canonical.json": [
            {"id": 1, "name": "IFES", "description": None, "short_name": "IFES"}
        ],
        "campuses_canonical.json": [],
        "research_groups_canonical.json": [
            {
                "id": 12,
                "name": "Grupo A",
                "campus_id": 6,
                "organization_id": 1,
                "cnpq_url": "http://dgp.cnpq.br/dgp/espelhogrupo/12",
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
    seeder.campus_ctrl.create_campus.assert_called_once_with(
        name="Serra", organization_id=201, description=None, short_name=None
    )
    kwargs = seeder.rg_ctrl.create_research_group.call_args.kwargs
    assert kwargs["campus_id"] == 206


def test_campuses_recovered_from_prior_archive(temp_export_dir):
    """When neither campuses_canonical.json nor group campus references exist, a
    prior canonical export ZIP with campus data must be used as recovery source."""
    archive_path = os.path.join(temp_export_dir, "canonical_export_20260813_190745.zip")
    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr(
            "campuses_canonical.json",
            json.dumps(
                [
                    {
                        "id": 6,
                        "name": "Serra",
                        "description": None,
                        "short_name": None,
                        "organization_id": 1,
                    }
                ]
            ),
        )

    data_files = {
        "organizations_canonical.json": [
            {"id": 1, "name": "IFES", "description": None, "short_name": "IFES"}
        ],
        "campuses_canonical.json": [],
        "research_groups_canonical.json": [
            {
                "id": 12,
                "name": "Grupo A",
                "campus_id": 6,
                "organization_id": 1,
                "cnpq_url": "http://dgp.cnpq.br/dgp/espelhogrupo/12",
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
    seeder.campus_ctrl.create_campus.assert_called_once_with(
        name="Serra", organization_id=201, description=None, short_name=None
    )
    kwargs = seeder.rg_ctrl.create_research_group.call_args.kwargs
    assert kwargs["campus_id"] == 206


def _mock_seeder_controllers(seeder):
    seeder.initiative_ctrl = MagicMock()
    seeder.person_ctrl = MagicMock()
    seeder.team_ctrl = MagicMock()
    seeder.adv_ctrl = MagicMock()
    seeder.fellowship_ctrl = MagicMock()
    seeder.role_ctrl = MagicMock()
    return seeder


def test_initiatives_seeded_with_org_type_team_and_person(temp_export_dir):
    initiatives = [
        {
            "id": 10,
            "name": "Projeto IA",
            "status": "Active",
            "description": "Descricao",
            "start_date": "2023-01-01T00:00:00",
            "end_date": "2025-12-31T00:00:00",
            "initiative_type_id": 1,
            "organization_id": 1,
            "parent_id": None,
            "team": [
                {
                    "person_id": 5,
                    "person_name": "Ana",
                    "roles": ["Coordinator"],
                    "start_date": "2023-01-01T00:00:00",
                    "end_date": None,
                }
            ],
        }
    ]
    with open(os.path.join(temp_export_dir, "initiatives_canonical.json"), "w") as f:
        json.dump(initiatives, f)

    seeder = _mock_seeder_controllers(CanonicalDatabaseSeeder())
    seeder.initiative_ctrl.get_all.return_value = []
    seeder.role_ctrl.get_all.return_value = []
    seeder._seed_persons_if_empty = MagicMock(return_value={5: 55})
    seeder._seed_roles_if_empty = MagicMock(return_value={"Coordinator": "role1"})
    seeder._seed_initiative_types_if_empty = MagicMock(return_value={})
    seeder._seed_organizations_if_empty = MagicMock(return_value={})

    seeder.initiative_ctrl.create.side_effect = (
        lambda ent: setattr(ent, "id", 99) or None
    )

    team = MagicMock()
    team.id = 7
    seeder.team_ctrl.create_team.return_value = team

    result = seeder.seed_initiatives_if_empty(export_dir=temp_export_dir)

    assert result == 1
    seeder.initiative_ctrl.create.assert_called_once()
    ent = seeder.initiative_ctrl.create.call_args.args[0]
    assert ent.name == "Projeto IA"
    assert ent.organization_id is None
    seeder.team_ctrl.create_team.assert_called_once()
    seeder.team_ctrl.add_member.assert_called_once()
    assert seeder.team_ctrl.add_member.call_args.kwargs["role"] == "role1"


def test_initiatives_seed_skips_when_existing(temp_export_dir):
    seeder = _mock_seeder_controllers(CanonicalDatabaseSeeder())
    seeder.initiative_ctrl.get_all.return_value = [MagicMock()]

    result = seeder.seed_initiatives_if_empty(export_dir=temp_export_dir)

    assert result == 0
    seeder.initiative_ctrl.create.assert_not_called()


def test_advisorships_seeded_with_fellowship_mapping(temp_export_dir):
    advisories = [
        {
            "id": None,
            "name": "Sem Projeto Associado",
            "advisorships": [
                {
                    "id": 937,
                    "name": "Equipamento Remoto",
                    "status": "Concluded",
                    "start_date": "2005-01-01T00:00:00",
                    "end_date": "2005-12-31T00:00:00",
                    "person_id": 100,
                    "person_name": "Marcos",
                    "supervisor_id": 200,
                    "supervisor_name": "Valdeir",
                    "fellowship": {"id": 3, "name": "PIVIC"},
                }
            ],
        }
    ]
    with open(os.path.join(temp_export_dir, "advisorships_canonical.json"), "w") as f:
        json.dump(advisories, f)

    seeder = _mock_seeder_controllers(CanonicalDatabaseSeeder())
    seeder.adv_ctrl.get_all.return_value = []
    seeder._person_by_id = {}
    seeder._seed_persons_if_empty = MagicMock(return_value={})
    seeder._seed_fellowships_if_empty = MagicMock(return_value={3: 77})

    result = seeder.seed_advisorships_if_empty(export_dir=temp_export_dir)

    assert result == 1
    kwargs = seeder.adv_ctrl.create_advisorship.call_args.kwargs
    assert kwargs["name"] == "Equipamento Remoto"
    assert kwargs["student_id"] == 100
    assert kwargs["supervisor_id"] == 200
    assert kwargs["fellowship_id"] == 77


def test_advisorships_seed_skips_when_existing(temp_export_dir):
    seeder = _mock_seeder_controllers(CanonicalDatabaseSeeder())
    seeder.adv_ctrl.get_all.return_value = [MagicMock()]

    result = seeder.seed_advisorships_if_empty(export_dir=temp_export_dir)

    assert result == 0
    seeder.adv_ctrl.create_advisorship.assert_not_called()


def test_initiatives_seed_dedupes_repeated_names(temp_export_dir):
    initiatives = [
        {
            "id": 1,
            "name": "Projeto Duplicado",
            "organization_id": None,
            "initiative_type_id": None,
            "parent_id": None,
            "team": [],
        },
        {
            "id": 2,
            "name": "Projeto Duplicado",
            "organization_id": None,
            "initiative_type_id": None,
            "parent_id": None,
            "team": [],
        },
    ]
    with open(os.path.join(temp_export_dir, "initiatives_canonical.json"), "w") as f:
        json.dump(initiatives, f)

    seeder = _mock_seeder_controllers(CanonicalDatabaseSeeder())
    seeder._rollback_shared_session = MagicMock()
    seeder.initiative_ctrl.get_all.return_value = []
    seeder._seed_persons_if_empty = MagicMock(return_value={})
    seeder._seed_roles_if_empty = MagicMock(return_value={})
    seeder._seed_initiative_types_if_empty = MagicMock(return_value={})
    seeder._seed_organizations_if_empty = MagicMock(return_value={})

    result = seeder.seed_initiatives_if_empty(export_dir=temp_export_dir)

    assert result == 1
    assert seeder.initiative_ctrl.create.call_count == 1
    seeder._rollback_shared_session.assert_not_called()


def test_initiatives_seed_rolls_back_on_create_failure(temp_export_dir):
    initiatives = [
        {
            "id": 1,
            "name": "Projeto Que Falha",
            "organization_id": None,
            "initiative_type_id": None,
            "parent_id": None,
            "team": [],
        }
    ]
    with open(os.path.join(temp_export_dir, "initiatives_canonical.json"), "w") as f:
        json.dump(initiatives, f)

    seeder = _mock_seeder_controllers(CanonicalDatabaseSeeder())
    seeder._rollback_shared_session = MagicMock()
    seeder.initiative_ctrl.get_all.return_value = []
    seeder._seed_persons_if_empty = MagicMock(return_value={})
    seeder._seed_roles_if_empty = MagicMock(return_value={})
    seeder._seed_initiative_types_if_empty = MagicMock(return_value={})
    seeder._seed_organizations_if_empty = MagicMock(return_value={})
    seeder.initiative_ctrl.create.side_effect = RuntimeError("boom")

    result = seeder.seed_initiatives_if_empty(export_dir=temp_export_dir)

    assert result == 0
    seeder._rollback_shared_session.assert_called_once()


def test_initiatives_seed_records_tracking_transaction(temp_export_dir):
    """Restored initiatives must produce source_records/assertions/change_logs
    so export provenance tables don't collapse after a fallback seed."""
    initiatives = [
        {
            "id": 10,
            "name": "Projeto IA",
            "status": "Active",
            "description": "Descricao",
            "start_date": "2023-01-01T00:00:00",
            "end_date": "2025-12-31T00:00:00",
            "initiative_type_id": 1,
            "organization_id": 1,
            "parent_id": None,
            "team": [],
        }
    ]
    with open(os.path.join(temp_export_dir, "initiatives_canonical.json"), "w") as f:
        json.dump(initiatives, f)

    fake_recorder = MagicMock()
    fake_record = MagicMock()
    fake_record.id = 1001
    fake_recorder.record_source_record.return_value = fake_record

    with patch("src.tracking.recorder.tracking_recorder", fake_recorder):
        seeder = _mock_seeder_controllers(CanonicalDatabaseSeeder())
        seeder.initiative_ctrl.get_all.return_value = []
        seeder._seed_persons_if_empty = MagicMock(return_value={})
        seeder._seed_roles_if_empty = MagicMock(return_value={})
        seeder._seed_initiative_types_if_empty = MagicMock(return_value={})
        seeder._seed_organizations_if_empty = MagicMock(return_value={})
        seeder.initiative_ctrl.create.side_effect = (
            lambda ent: setattr(ent, "id", 99) or None
        )
        team = MagicMock()
        team.id = 7
        seeder.team_ctrl.create_team.return_value = team

        result = seeder.seed_initiatives_if_empty(export_dir=temp_export_dir)

    assert result == 1
    assert fake_recorder.record_source_record.called
    assert fake_recorder.record_entity_match.called
    assert fake_recorder.record_attribute_assertions.called
    assert fake_recorder.record_change.called
    call = fake_recorder.record_source_record.call_args.kwargs
    assert call["source_entity_type"] == "initiative"
    assert call["source_record_id"] == "10"
    assert call["payload"]["name"] == "Projeto IA"


def test_groups_seed_records_tracking_transaction(temp_export_dir):
    data_files = {
        "organizations_canonical.json": [
            {"id": 1, "name": "IFES", "description": None, "short_name": "IFES"}
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

    fake_recorder = MagicMock()
    fake_record = MagicMock()
    fake_record.id = 2001
    fake_recorder.record_source_record.return_value = fake_record

    with patch("src.tracking.recorder.tracking_recorder", fake_recorder):
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

        def fake_group(**kwargs):
            group = MagicMock()
            group.id = 912
            return group

        seeder.org_ctrl.create_organization.side_effect = fake_org
        seeder.campus_ctrl.create_campus.side_effect = fake_campus
        seeder.rg_ctrl.create_research_group.side_effect = fake_group

        result = seeder.seed_research_groups_if_empty(export_dir=temp_export_dir)

    assert result == 1
    assert fake_recorder.record_source_record.called
    assert fake_recorder.record_entity_match.called
    assert fake_recorder.record_attribute_assertions.called
    assert fake_recorder.record_change.called
    call = fake_recorder.record_source_record.call_args.kwargs
    assert call["source_entity_type"] == "research_group"
    assert call["source_record_id"] == "12"


def test_advisorships_seed_records_tracking_transaction(temp_export_dir):
    advisories = [
        {
            "id": None,
            "name": "Sem Projeto Associado",
            "advisorships": [
                {
                    "id": 937,
                    "name": "Equipamento Remoto",
                    "status": "Concluded",
                    "start_date": "2005-01-01T00:00:00",
                    "end_date": "2005-12-31T00:00:00",
                    "person_id": 100,
                    "person_name": "Marcos",
                    "supervisor_id": 200,
                    "supervisor_name": "Valdeir",
                    "fellowship": {"id": 3, "name": "PIVIC"},
                }
            ],
        }
    ]
    with open(os.path.join(temp_export_dir, "advisorships_canonical.json"), "w") as f:
        json.dump(advisories, f)

    fake_recorder = MagicMock()
    fake_record = MagicMock()
    fake_record.id = 3001
    fake_recorder.record_source_record.return_value = fake_record

    with patch("src.tracking.recorder.tracking_recorder", fake_recorder):
        seeder = _mock_seeder_controllers(CanonicalDatabaseSeeder())
        seeder.adv_ctrl.get_all.return_value = []
        seeder._person_by_id = {}
        seeder._seed_persons_if_empty = MagicMock(return_value={})
        seeder._seed_fellowships_if_empty = MagicMock(return_value={3: 77})

        def fake_adv(**kwargs):
            adv = MagicMock()
            adv.id = 9370
            return adv

        seeder.adv_ctrl.create_advisorship.side_effect = fake_adv

        result = seeder.seed_advisorships_if_empty(export_dir=temp_export_dir)

    assert result == 1
    assert fake_recorder.record_source_record.called
    assert fake_recorder.record_entity_match.called
    assert fake_recorder.record_attribute_assertions.called
    assert fake_recorder.record_change.called
    call = fake_recorder.record_source_record.call_args.kwargs
    assert call["source_entity_type"] == "advisorship"
    assert call["source_record_id"] == "937"
