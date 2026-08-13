from pathlib import Path

from loguru import logger


class ProvenanceTracker:
    """
    Manages reading, writing, and clearing data origin marker files in data/exports/.
    Valid origins: 'LIVE', 'ZIP ANTERIOR', 'PARCIAL', 'VAZIO'.
    """

    VALID_ORIGINS = {"LIVE", "ZIP ANTERIOR", "PARCIAL", "VAZIO"}

    @classmethod
    def set_provenance(
        cls, phase_name: str, origin: str, export_dir: str = "data/exports"
    ) -> None:
        if origin not in cls.VALID_ORIGINS:
            logger.warning(
                "Invalid provenance origin '{}' for phase '{}'. Defaulting to LIVE.",
                origin,
                phase_name,
            )
            origin = "LIVE"

        target_path = Path(export_dir).resolve()
        target_path.mkdir(parents=True, exist_ok=True)
        marker_file = target_path / f".{phase_name}_provenance"

        try:
            marker_file.write_text(origin, encoding="utf-8")
        except OSError as exc:
            logger.warning(
                "Failed to write provenance marker for {}: {}", phase_name, exc
            )

    @classmethod
    def get_provenance(cls, phase_name: str, export_dir: str = "data/exports") -> str:
        marker_file = Path(export_dir).resolve() / f".{phase_name}_provenance"
        if not marker_file.is_file():
            return "LIVE"

        try:
            val = marker_file.read_text(encoding="utf-8").strip()
            return val if val in cls.VALID_ORIGINS else "LIVE"
        except OSError:
            return "LIVE"

    @classmethod
    def clear_provenance(cls, export_dir: str = "data/exports") -> None:
        target_path = Path(export_dir).resolve()
        if not target_path.is_dir():
            return

        for marker_file in target_path.glob(".*_provenance"):
            try:
                marker_file.unlink()
            except OSError:
                pass
