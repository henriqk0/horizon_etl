"""
Convert the JSON canonical exports into a Parquet layout for storage/consumption.

Layout produced in the destination directory:

* array-of-objects file  ->  ``<name>.parquet`` (+ ``<name>.cols.json`` sidecar).
* node-link graph file    ->  ``<name>.nodes.parquet`` + ``<name>.edges.parquet``
  (+ their ``.cols.json`` sidecars) + ``<name>.meta.json``.
* other small object (marts, summaries, ``_meta``)  ->  copied as ``<name>.json``.

Columns that contain ANY nested (object/list) value are fully JSON-encoded:
**every** non-null cell is stored via ``json.dumps()`` — not just the nested
ones. This preserves type fidelity for mixed-type columns (e.g. ``value_json``
can hold ``null``, a plain string, an integer, AND a list in the same column).
The ``<name>.cols.json`` sidecar (``{"json_columns": [...]}``) tells the reader
EXACTLY which columns were JSON-encoded, so it never has to guess (see the
dashboard's parquet plugin). The reader MUST call ``json.loads()`` on **every**
cell of a column listed in the sidecar, not just on cells starting with ``{``
or ``[``. Id-like columns are pinned to a nullable integer dtype so they don't
round-trip as floats (e.g. ``4737.0``).

Round-trips losslessly for all canonical/graph tables. Usage::

    python -m src.scripts.export_parquet --src data/exports --dst data/exports_parquet
"""

import argparse
import glob
import json
import os
import shutil
import tempfile
import zipfile

import pandas as pd
from loguru import logger

COMPRESSION = "zstd"
NESTED_TYPES = (dict, list)


def _is_id_column(name: str) -> bool:
    return name == "id" or name.endswith("_id")


def _has_nested_values(series: pd.Series) -> bool:
    """Check if any non-null value in the series is a dict or list."""
    non_null = series.dropna()
    if len(non_null) == 0:
        return False
    for v in non_null:
        if isinstance(v, NESTED_TYPES):
            return True
    return False


def _encode_columns(df: pd.DataFrame) -> list:
    """JSON-encode every non-null cell of columns that contain any nested value,
    and pins id-like columns to a nullable integer dtype.
    Returns the list of columns that were JSON-encoded."""
    json_columns = []
    for col in df.columns:
        if _has_nested_values(df[col]):
            df[col] = [
                json.dumps(v, ensure_ascii=False) if v is not None else v
                for v in df[col]
            ]
            json_columns.append(col)
        elif _is_id_column(col):
            try:
                df[col] = pd.to_numeric(df[col]).astype("Int64")
            except (ValueError, TypeError):
                pass  # non-numeric id (already a string) — leave as is
    return json_columns


def _write_table(rows: list, path: str) -> None:
    df = pd.json_normalize(rows, max_level=0)
    json_columns = _encode_columns(df)
    df.to_parquet(path, compression=COMPRESSION, index=False)
    sidecar = path[: -len(".parquet")] + ".cols.json"
    with open(sidecar, "w", encoding="utf-8") as fh:
        json.dump({"json_columns": json_columns}, fh, ensure_ascii=False)


def _is_graph(data) -> bool:
    return (
        isinstance(data, dict)
        and isinstance(data.get("graph"), dict)
        and "nodes" in data["graph"]
        and "edges" in data["graph"]
    )


def convert_file(path: str, dst_dir: str) -> str:
    name = os.path.basename(path)
    stem = name[:-5] if name.endswith(".json") else name
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)

    if isinstance(data, list) and data and isinstance(data[0], dict):
        _write_table(data, os.path.join(dst_dir, f"{stem}.parquet"))
        return "table"

    if _is_graph(data):
        graph = data["graph"]
        _write_table(graph["nodes"], os.path.join(dst_dir, f"{stem}.nodes.parquet"))
        _write_table(graph["edges"], os.path.join(dst_dir, f"{stem}.edges.parquet"))
        meta = {
            "metadata": data.get("metadata"),
            "graph_stats": data.get("graph_stats"),
            "graph": {
                "directed": graph.get("directed"),
                "multigraph": graph.get("multigraph"),
                "graph": graph.get("graph"),
            },
        }
        with open(
            os.path.join(dst_dir, f"{stem}.meta.json"), "w", encoding="utf-8"
        ) as fh:
            json.dump(meta, fh, ensure_ascii=False)
        return "graph"

    # small nested object (mart/summary/_meta): keep as JSON
    shutil.copy2(path, os.path.join(dst_dir, name))
    return "json"


def _find_or_extract_jsons(src: str) -> str:
    """Return a directory with ``*.json`` files.

    If loose JSON files exist in *src* they are used directly.
    Otherwise ``export.zip`` in *src* is extracted to a temporary directory
    and that path is returned. For backward compatibility, if ``export.zip``
    is absent the most recent ``canonical_export_*.zip`` is used instead.
    The caller is responsible for cleaning up the temporary directory.
    """
    jsons = sorted(glob.glob(os.path.join(src, "*.json")))
    if jsons:
        return src

    export_zip = os.path.join(src, "export.zip")
    if os.path.exists(export_zip):
        archive = export_zip
    else:
        zips = sorted(
            glob.glob(os.path.join(src, "canonical_export_*.zip")),
            key=os.path.getmtime,
            reverse=True,
        )
        if not zips:
            logger.warning("No JSON files or export.zip archive found in {}.", src)
            return ""
        archive = zips[0]

    logger.info("No loose JSONs found — extracting {} …", os.path.basename(archive))
    tmp = tempfile.mkdtemp(prefix="export_parquet_")
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(tmp)
    logger.info("Extracted {} files from ZIP.", len(os.listdir(tmp)))
    return tmp


def convert_dir(src: str, dst: str) -> dict:
    os.makedirs(dst, exist_ok=True)
    stats = {"table": 0, "graph": 0, "json": 0, "error": 0}

    src_dir = _find_or_extract_jsons(src)
    if not src_dir:
        return stats

    try:
        for path in sorted(glob.glob(os.path.join(src_dir, "*.json"))):
            try:
                stats[convert_file(path, dst)] += 1
            except Exception as exc:
                logger.warning("Failed converting {}: {}", os.path.basename(path), exc)
                stats["error"] += 1
    finally:
        if src_dir != src:
            shutil.rmtree(src_dir, ignore_errors=True)

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert JSON exports to Parquet layout."
    )
    parser.add_argument("--src", default="data/exports")
    parser.add_argument("--dst", default="data/exports_parquet")
    args = parser.parse_args()
    stats = convert_dir(args.src, args.dst)
    logger.info("Parquet conversion complete: {} -> {}", stats, args.dst)


if __name__ == "__main__":
    main()
