"""Unit and integration tests for SigPesq project PDF download and Mistral AI extraction."""

import json
import os
from unittest.mock import MagicMock, patch


def test_environment_validation_alias():
    """Verify SIGPESQ_USER and MISTRAL_KEY alias handling."""
    from src.adapters.sources.sigpesq.adapter import SigPesqAdapter

    with patch.dict(
        os.environ,
        {
            "SIGPESQ_USER": "test_user",
            "SIGPESQ_PASSWORD": "test_password",
            "MISTRAL_API_KEY": "test_mistral_key",
        },
        clear=True,
    ):
        adapter = SigPesqAdapter(download_dir="data/raw/sigpesq/test_projects")
        adapter._validate_environment()
        assert os.environ.get("SIGPESQ_USERNAME") == "test_user"
        assert os.environ.get("MISTRAL_KEY") == "test_mistral_key"


def test_download_project_pdfs_orchestration():
    """Verify download_project_pdfs calls _trigger_download with ProjectFilesDownloadStrategy."""
    from src.adapters.sources.sigpesq.adapter import SigPesqAdapter

    adapter = SigPesqAdapter()
    with (
        patch.object(adapter, "_validate_environment"),
        patch.object(adapter, "_trigger_download") as mock_trigger,
    ):
        success = adapter.download_project_pdfs(
            download_dir="data/raw/sigpesq/test_projects",
            file_label="Projeto",
            limit=5,
            skip_existing=True,
        )
        assert success is True
        assert mock_trigger.called
        kwargs = mock_trigger.call_args[1]
        assert "download_strategies" in kwargs
        strategy = kwargs["download_strategies"][0]
        assert strategy.file_label == "Projeto"
        assert strategy.limit == 5
        assert strategy.skip_existing is True


def test_lgpd_cpf_masking():
    """Verify LGPD CPF masking in extracted payloads."""
    from src.adapters.sources.sigpesq.mistral_extractor import (
        apply_lgpd_masking,
        mask_cpf,
    )

    assert mask_cpf("12345678901") == "***.456.789-**"
    assert mask_cpf("123.456.789-01") == "***.456.789-**"

    payload = {
        "coordenador": {"nome": "Maria", "cpf": "123.456.789-01"},
        "equipe": [{"nome": "João", "cpf": "98765432100"}],
    }

    masked = apply_lgpd_masking(payload)
    assert masked["coordenador"]["cpf"] == "***.456.789-**"
    assert masked["equipe"][0]["cpf"] == "***.654.321-**"


def test_sigpesq_project_extractor_file_mock(tmp_path):
    """Verify SigPesqProjectExtractor.extract_file with mock ProjectExtractor."""
    from src.adapters.sources.sigpesq.mistral_extractor import SigPesqProjectExtractor

    pdf_file = tmp_path / "PJ 6020.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 mock content")

    out_dir = tmp_path / "exports"

    mock_projeto = MagicMock()
    mock_projeto.model_dump.return_value = {
        "codigo": "6020",
        "titulo": "Projeto Teste",
        "coordenador": {"cpf": "11122233344"},
        "equipe": [],
    }

    with patch(
        "agent_sigpesq.extraction.mistral_extractor.ProjectExtractor.extract_project",
        return_value=mock_projeto,
    ):
        extractor = SigPesqProjectExtractor(api_key="mock_key")
        res_file = extractor.extract_file(str(pdf_file), str(out_dir))

        assert os.path.exists(res_file)
        with open(res_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["codigo"] == "6020"
        assert data["coordenador"]["cpf"] == "***.222.333-**"


def test_extract_projects_flow_mock(tmp_path):
    """Verify extract_projects_flow orchestration with mocked download, extraction, and enrichment."""
    from src.flows.sigpesq.extract_projects import extract_projects_flow

    raw_dir = tmp_path / "raw"
    export_dir = tmp_path / "exports"
    raw_dir.mkdir()
    export_dir.mkdir()

    with (
        patch(
            "src.adapters.sources.sigpesq.adapter.SigPesqAdapter.download_project_pdfs",
            return_value=True,
        ),
        patch(
            "src.adapters.sources.sigpesq.mistral_extractor.SigPesqProjectExtractor.process_directory",
            return_value={"processed": 1, "errors": 0},
        ),
        patch(
            "src.flows.sigpesq.extract_projects.enrich_projects_flow",
            return_value={"matched": 1, "created": 0},
        ),
    ):
        result = extract_projects_flow(
            download_dir=str(raw_dir),
            export_dir=str(export_dir),
            skip_download=False,
            run_enrichment=True,
        )

        assert result["download_success"] is True
        assert result["extraction"]["processed"] == 1
        assert result["enrichment_stats"]["matched"] == 1
