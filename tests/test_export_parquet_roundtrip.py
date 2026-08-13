import json
import math
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from src.scripts.export_parquet import _find_or_extract_jsons, convert_dir, convert_file

EXPORTS_DIR = Path("data/exports")


def _resolve_zip() -> Path:
    export_zip = EXPORTS_DIR / "export.zip"
    if export_zip.exists():
        return export_zip
    ts_zips = sorted(p for p in EXPORTS_DIR.glob("canonical_export_*.zip"))
    if ts_zips:
        return ts_zips[-1]
    raise FileNotFoundError(
        f"No export.zip or canonical_export_*.zip found in {EXPORTS_DIR}"
    )


def _is_noneish(v):
    return v is None or (isinstance(v, float) and math.isnan(v))


def _decode_json_cols(df: pd.DataFrame, json_cols: list[str]) -> pd.DataFrame:
    for col in json_cols:
        if col in df.columns:
            df[col] = df[col].apply(
                lambda v: json.loads(v) if isinstance(v, str) else v
            )
    return df


def test_roundtrip_all_files() -> None:
    """Every canonical JSON round-trips losslessly through the parquet converter.

    Uses the same source resolution as the production script:
    loose JSONs if available, otherwise last canonical ZIP.
    """
    src_dir = _find_or_extract_jsons(str(EXPORTS_DIR))
    assert src_dir, f"No source data found in {EXPORTS_DIR}"

    dst_dir = tempfile.mkdtemp()
    errors = []

    try:
        for path in sorted(Path(src_dir).glob("*.json")):
            name = path.name
            raw = json.loads(path.read_text(encoding="utf-8"))
            result_type = convert_file(str(path), dst_dir)

            if result_type == "json":
                with open(os.path.join(dst_dir, name)) as f:
                    rt = json.load(f)
                if raw != rt:
                    errors.append(f"{name}: copied JSON differs")

            elif result_type == "graph":
                stem = name[:-5]
                nodes = pd.read_parquet(os.path.join(dst_dir, f"{stem}.nodes.parquet"))
                edges = pd.read_parquet(os.path.join(dst_dir, f"{stem}.edges.parquet"))
                with open(os.path.join(dst_dir, f"{stem}.meta.json")) as f:
                    meta = json.load(f)

                if len(raw["graph"]["nodes"]) != len(nodes):
                    errors.append(f"{name}: node count mismatch")
                if len(raw["graph"]["edges"]) != len(edges):
                    errors.append(f"{name}: edge count mismatch")
                for key in ("directed", "multigraph", "graph"):
                    if raw["graph"][key] != meta["graph"][key]:
                        errors.append(f"{name}: graph.{key} mismatch")

            elif result_type == "table":
                stem = name[:-5]
                with open(os.path.join(dst_dir, f"{stem}.cols.json")) as f:
                    cols_meta = json.load(f)
                df = pd.read_parquet(os.path.join(dst_dir, f"{stem}.parquet"))
                df = _decode_json_cols(df, cols_meta.get("json_columns", []))
                rt = df.to_dict("records")

                if len(raw) != len(rt):
                    errors.append(f"{name}: row count {len(raw)} -> {len(rt)}")
                    continue

                for i in range(len(raw)):
                    o, r = raw[i], rt[i]
                    for k in o:
                        ov, rv = o[k], r.get(k)
                        if ov == rv:
                            continue
                        if _is_noneish(ov) and _is_noneish(rv):
                            continue
                        errors.append(
                            f"{name}: row {i}, col {k}: "
                            f"{ov!r} ({type(ov).__name__}) "
                            f"!= {rv!r} ({type(rv).__name__})"
                        )

    finally:
        shutil.rmtree(dst_dir, ignore_errors=True)
        if src_dir != str(EXPORTS_DIR):
            shutil.rmtree(src_dir, ignore_errors=True)

    if errors:
        for e in errors[:20]:
            print(e)
        if len(errors) > 20:
            print(f"... and {len(errors) - 20} more errors")
        pytest.fail(f"{len(errors)} round-trip mismatch(es)")


def test_fallback_to_zip_no_loose_jsons(tmp_path: Path) -> None:
    """_find_or_extract_jsons extracts the ZIP when no loose JSONs exist."""
    export_zip = _resolve_zip()
    shutil.copy2(export_zip, tmp_path / export_zip.name)

    result = _find_or_extract_jsons(str(tmp_path))
    assert result != str(tmp_path)
    assert os.path.isdir(result)
    files = os.listdir(result)
    assert any(f.endswith(".json") for f in files)
    shutil.rmtree(result, ignore_errors=True)


def test_fallback_with_loose_jsons(tmp_path: Path) -> None:
    """_find_or_extract_jsons returns src when loose JSONs exist."""
    export_zip = _resolve_zip()

    with zipfile.ZipFile(export_zip) as zf:
        members = [n for n in zf.namelist() if n.endswith(".json") and "/" not in n]
        for name in members[:3]:
            (tmp_path / name).write_text(zf.read(name).decode())

    result = _find_or_extract_jsons(str(tmp_path))
    assert result == str(tmp_path)


def test_fallback_no_jsons_no_zip(tmp_path: Path) -> None:
    """_find_or_extract_jsons returns empty string when nothing found."""
    result = _find_or_extract_jsons(str(tmp_path))
    assert result == ""


def test_convert_dir_empty_src(tmp_path: Path) -> None:
    """convert_dir returns empty stats when src has no valid data."""
    empty = tmp_path / "empty"
    empty.mkdir()
    dst = tmp_path / "dst"
    stats = convert_dir(str(empty), str(dst))
    assert stats == {"table": 0, "graph": 0, "json": 0, "error": 0}
