import zipfile
from pathlib import Path
from typing import Any

from loguru import logger


class ExportCacheBootstrapper:
    """
    Discovers the most recent export ZIP archive and extracts its contents
    into the target export directory prior to ingestion pipeline execution.
    """

    DEFAULT_PATTERNS = (
        "novo_backup.zip",
        "novo_backup*.zip",
        "export.zip",
        "canonical_export_*.zip",
        "exports_canonical*.zip",
    )

    def find_latest_archive(self, search_dirs: list[str] | None = None) -> Path | None:
        """
        Scans search_dirs (default: ['data/exports', '.']) for matching archives.
        Returns Path to newest file by mtime, or None if none found.
        """
        if search_dirs is None:
            search_dirs = ["data/exports", "."]

        for sdir in search_dirs:
            pdir = Path(sdir).resolve()
            if not pdir.is_dir():
                continue

            candidates: list[Path] = []
            for pattern in self.DEFAULT_PATTERNS:
                for match in pdir.glob(pattern):
                    if match.is_file() and match.stat().st_size > 0:
                        candidates.append(match)

            if candidates:
                candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                latest = candidates[0]
                logger.info(
                    "Discovered latest export ZIP archive in {}: {}",
                    sdir,
                    latest.name,
                )
                return latest

        return None

    def bootstrap(
        self,
        target_dir: str = "data/exports",
        search_dirs: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Finds and extracts the latest archive into target_dir. Retains source ZIP.
        Returns summary dictionary with keys: restored (bool), archive_used (str),
        files_extracted (int), warning (str|None).
        """
        target_path = Path(target_dir).resolve()
        target_path.mkdir(parents=True, exist_ok=True)

        archive_path = self.find_latest_archive(search_dirs)

        if not archive_path:
            msg = f"No prior export ZIP found in {search_dirs or ['data/exports', '.']}; starting with empty cache."
            logger.info(msg)
            return {
                "restored": False,
                "archive_used": None,
                "files_extracted": 0,
                "warning": msg,
            }

        try:
            with zipfile.ZipFile(archive_path, "r") as zf:
                namelist = zf.namelist()
                self._safe_extract_all(zf, target_path)

            logger.info(
                "Successfully restored {} files from {} into {}",
                len(namelist),
                archive_path.name,
                target_path,
            )
            return {
                "restored": True,
                "archive_used": str(archive_path),
                "files_extracted": len(namelist),
                "warning": None,
            }
        except (zipfile.BadZipFile, OSError, Exception) as exc:
            msg = f"Failed to decompress export ZIP archive {archive_path.name}: {exc}"
            logger.warning(msg)
            return {
                "restored": False,
                "archive_used": str(archive_path),
                "files_extracted": 0,
                "warning": msg,
            }

    @staticmethod
    def _safe_extract_all(zf: zipfile.ZipFile, target_path: Path) -> None:
        """Extracts every member of zf into target_path, rejecting any entry
        whose resolved path would land outside target_path ("Zip Slip",
        CWE-22) — e.g. a member name containing "../" or an absolute path.
        """
        target_root = target_path.resolve()
        for member in zf.infolist():
            member_path = (target_root / member.filename).resolve()
            if member_path != target_root and target_root not in member_path.parents:
                raise ValueError(
                    f"Refusing to extract unsafe zip member outside target "
                    f"directory: {member.filename!r}"
                )
        zf.extractall(target_path)
