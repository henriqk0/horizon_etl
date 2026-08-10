"""Adapter module wrapping agent_sigpesq Mistral project extraction components."""

import glob
import json
import os
import re
from typing import Any, Dict, Optional

from loguru import logger


def mask_cpf(cpf_str: Optional[str]) -> Optional[str]:
    """Masks CPF string to comply with LGPD Principle V (e.g. ***.123.456-**)."""
    if not cpf_str or not isinstance(cpf_str, str):
        return cpf_str
    digits = re.sub(r"\D", "", cpf_str)
    if len(digits) == 11:
        return f"***.{digits[3:6]}.{digits[6:9]}-**"
    return "***.***.***-**"


def apply_lgpd_masking(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Applies LGPD PII anonymization to coordinator and team member CPF fields."""
    if not isinstance(payload, dict):
        return payload

    coordenador = payload.get("coordenador")
    if isinstance(coordenador, dict) and coordenador.get("cpf"):
        coordenador["cpf"] = mask_cpf(coordenador["cpf"])

    equipe = payload.get("equipe")
    if isinstance(equipe, list):
        for membro in equipe:
            if isinstance(membro, dict) and membro.get("cpf"):
                membro["cpf"] = mask_cpf(membro["cpf"])

    return payload


class SigPesqProjectExtractor:
    """Encapsulates Mistral AI PDF extraction, OCR fallback, and batch processing."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = (
            api_key or os.getenv("MISTRAL_KEY") or os.getenv("MISTRAL_API_KEY")
        )

    def extract_file(self, pdf_path: str, output_dir: str) -> str:
        """Extracts structured project report from a single PDF and writes JSON file."""
        from agent_sigpesq.extraction.mistral_extractor import ProjectExtractor

        extractor = ProjectExtractor(api_key=self.api_key)
        projeto = extractor.extract_project(pdf_path)

        data = projeto.model_dump(by_alias=True)
        data = apply_lgpd_masking(data)

        stem = os.path.splitext(os.path.basename(pdf_path))[0]
        os.makedirs(output_dir, exist_ok=True)
        out_path = os.path.join(output_dir, f"{stem}.json")

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"Extracted {pdf_path} -> {out_path}")
        return out_path

    def process_directory(
        self,
        pdf_dir: str = "data/raw/sigpesq/projects",
        output_dir: str = "data/exports/project_sigpesq_files_json",
        use_batch: bool = False,
    ) -> Dict[str, int]:
        pdf_paths = sorted(
            set(
                glob.glob(os.path.join(pdf_dir, "**", "*.pdf"), recursive=True)
                + glob.glob(os.path.join(pdf_dir, "*.pdf"))
            )
        )

        if not pdf_paths:
            logger.info(f"No PDF files found in {pdf_dir}.")
            return {"processed": 0, "errors": 0}

        processed = 0
        errors = 0

        if use_batch:
            from agent_sigpesq.extraction.batch_extractor import BatchProjectExtractor

            logger.info(f"Submitting {len(pdf_paths)} PDFs to Mistral Batch API...")
            batch_extractor = BatchProjectExtractor(api_key=self.api_key)
            jsonl_text, meta_map, skipped_scanned = batch_extractor.build_requests(
                pdf_paths
            )

            if jsonl_text.strip():
                try:
                    job_id = batch_extractor.submit(jsonl_text)
                    logger.info(f"Created Mistral batch job: {job_id}")

                    # Collect available batch results
                    job = batch_extractor.get_job(job_id)
                    written, errs = batch_extractor.collect_results(
                        job, meta_map, output_dir
                    )
                    processed += written
                    errors += errs
                except Exception as exc:
                    logger.warning(
                        f"Batch execution failed or pending: {exc}. Falling back to sync extraction."
                    )
                    skipped_scanned = pdf_paths

            # Process scanned or fallback PDFs synchronously
            for pdf_path in skipped_scanned:
                try:
                    self.extract_file(pdf_path, output_dir)
                    processed += 1
                except Exception as exc:
                    logger.error(f"Error extracting {pdf_path}: {exc}")
                    errors += 1
        else:
            for pdf_path in pdf_paths:
                try:
                    self.extract_file(pdf_path, output_dir)
                    processed += 1
                except Exception as exc:
                    logger.error(f"Error extracting {pdf_path}: {exc}")
                    errors += 1

        # Post-process all output JSONs in output_dir to enforce LGPD masking
        for json_path in glob.glob(os.path.join(output_dir, "*.json")):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    content = json.load(f)
                masked_content = apply_lgpd_masking(content)
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(masked_content, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

        logger.info(
            f"Finished directory processing. Processed: {processed}, Errors: {errors}"
        )
        return {"processed": processed, "errors": errors}
