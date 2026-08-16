import zipfile
from pathlib import Path
from typing import Any

from loguru import logger


class ExportCacheBootstrapper:
    """
    Discovers the most recent export ZIP archive and extracts its contents
    into the target export directory prior to ingestion pipeline execution.
    """

    DEFAULT_PATTERNS = ("canonical_export_*.zip", "exports_canonical.zip", "export.zip")

    @staticmethod
    def _detect_prefix(namelist: list[str]) -> str:
        """
        Returns a common leading directory prefix to strip, e.g. "data/" when
        the archive was created from the repository root. Returns "" if the
        entries are already relative to the export directory.
        """
        entries = [n.rstrip("/") for n in namelist if n.rstrip("/")]
        if not entries:
            return ""
        first = entries[0].split("/")[0]
        if all(e.split("/")[0] == first for e in entries):
            return first + "/"
        return ""

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
                prefix = self._detect_prefix(namelist)
                if prefix:
                    logger.info(
                        "Stripping common '{}' prefix from archive entries", prefix
                    )
                for member in zf.namelist():
                    relative = (member[len(prefix) :] if prefix else member).lstrip("/")
                    if not relative:
                        continue
                    dest = target_path / relative
                    if not str(dest.resolve()).startswith(str(target_path.resolve())):
                        logger.warning("Skipping unsafe archive entry: {}", member)
                        continue
                    if member.endswith("/"):
                        dest.mkdir(parents=True, exist_ok=True)
                        continue
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, open(dest, "wb") as out:
                        out.write(src.read())

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
