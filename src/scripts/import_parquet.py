"""
Convert a Parquet dashboard data layout back into loose JSON canonical exports.

Reverses the encoding done by ``export_parquet.py``. Mirrors the exact
revival logic of the dashboard's own Vite build plugin
(``horizon_dashboard/parquet-plugin.mjs``):

* tables       ``<name>.parquet``                                -> ``<name>.json``
* graphs       ``<name>.nodes.parquet`` + ``<name>.edges.parquet``
               + ``<name>.meta.json``                             -> ``<name>.json``
* everything else already a loose ``.json`` file (marts, summaries,
  ``_meta.json``) is copied through unchanged.

Column revival: if a ``<name>.cols.json`` sidecar (``{"json_columns": [...]}``)
sits next to the parquet file, its columns are ``json.loads()``-decoded
exactly. When no sidecar is present — the normal case for a folder pulled
from a deployed dashboard build, which doesn't ship the sidecars — falls back
to the SAME heuristic the dashboard plugin itself uses at build time: any
string value starting with ``[`` or ``{`` is parsed as JSON, everything else
is left as-is. This means the JSON produced here matches what the live
dashboard actually renders, including its known limitation that a JSON-array
column also holding plain string cells (a rare mixed-type column) round-trips
those cells as a quoted JSON string literal rather than the bare string.

Usage::

    python -m src.scripts.import_parquet --src ../horizon_dashboard/src/data --dst data/exports_from_dashboard
"""

import argparse
import glob
import json
import os
import shutil

import numpy as np
import pandas as pd
from loguru import logger


def _load_sidecar_columns(parquet_path: str):
    sidecar = parquet_path[: -len(".parquet")] + ".cols.json"
    if not os.path.exists(sidecar):
        return None
    with open(sidecar, encoding="utf-8") as fh:
        return set(json.load(fh).get("json_columns", []))


def _normalize_scalar(v):
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.floating):
        return float(v)
    if isinstance(v, np.bool_):
        return bool(v)
    return v


def _parse_maybe_json(v):
    if not isinstance(v, str):
        return _normalize_scalar(v)
    if v[:1] not in ("[", "{"):
        return v
    try:
        return json.loads(v)
    except (ValueError, TypeError):
        return v


def _revive_cell(v, col: str, json_cols):
    if v is None or (not isinstance(v, (list, dict)) and pd.isna(v)):
        return None
    if json_cols is not None:
        return json.loads(v) if col in json_cols else _normalize_scalar(v)
    return _parse_maybe_json(v)


def read_table(path: str) -> list:
    df = pd.read_parquet(path)
    json_cols = _load_sidecar_columns(path)
    return [
        {col: _revive_cell(v, col, json_cols) for col, v in row.items()}
        for row in df.to_dict(orient="records")
    ]


def _sanitize_non_finite(obj):
    """Replace NaN/Infinity/-Infinity with None (recursively).

    ``json.dumps`` emits these as bare ``NaN``/``Infinity`` tokens by default
    (a Python-only, non-standard extension), which strict JSON parsers such
    as the dashboard's Vite ``vite:json`` plugin reject outright. They only
    ever mean "missing value" here (e.g. an empty spreadsheet cell captured
    in a raw ``raw_payload_json`` blob), so ``null`` is the correct revival.
    """
    if isinstance(obj, float):
        return None if (obj != obj or obj in (float("inf"), float("-inf"))) else obj
    if isinstance(obj, dict):
        return {k: _sanitize_non_finite(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_non_finite(v) for v in obj]
    return obj


def convert_table(path: str, dst_dir: str) -> str:
    stem = os.path.basename(path)[: -len(".parquet")]
    rows = _sanitize_non_finite(read_table(path))
    out_path = os.path.join(dst_dir, f"{stem}.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False)
    return out_path


def convert_graph(stem: str, src_dir: str, dst_dir: str) -> str:
    nodes = read_table(os.path.join(src_dir, f"{stem}.nodes.parquet"))
    edges = read_table(os.path.join(src_dir, f"{stem}.edges.parquet"))
    meta_path = os.path.join(src_dir, f"{stem}.meta.json")
    meta = {}
    if os.path.exists(meta_path):
        with open(meta_path, encoding="utf-8") as fh:
            meta = json.load(fh)
    assembled = _sanitize_non_finite(
        {
            "metadata": meta.get("metadata"),
            "graph_stats": meta.get("graph_stats"),
            "graph": {**(meta.get("graph") or {}), "nodes": nodes, "edges": edges},
        }
    )
    out_path = os.path.join(dst_dir, f"{stem}.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(assembled, fh, ensure_ascii=False)
    return out_path


def convert_dir(src: str, dst: str) -> dict:
    os.makedirs(dst, exist_ok=True)
    stats = {"table": 0, "graph": 0, "json": 0, "error": 0}

    graph_stems = set()
    plain_tables = []
    for path in sorted(glob.glob(os.path.join(src, "*.parquet"))):
        name = os.path.basename(path)
        if name.endswith(".nodes.parquet"):
            graph_stems.add(name[: -len(".nodes.parquet")])
        elif name.endswith(".edges.parquet"):
            graph_stems.add(name[: -len(".edges.parquet")])
        else:
            plain_tables.append(path)

    for stem in sorted(graph_stems):
        try:
            convert_graph(stem, src, dst)
            stats["graph"] += 1
        except Exception as exc:
            logger.warning("Failed converting graph {}: {}", stem, exc)
            stats["error"] += 1

    for path in plain_tables:
        try:
            convert_table(path, dst)
            stats["table"] += 1
        except Exception as exc:
            logger.warning("Failed converting {}: {}", os.path.basename(path), exc)
            stats["error"] += 1

    for path in glob.glob(os.path.join(src, "*.json")):
        name = os.path.basename(path)
        if name.endswith(".cols.json") or name.endswith(".meta.json"):
            continue
        shutil.copy2(path, os.path.join(dst, name))
        stats["json"] += 1

    for entry in os.listdir(src):
        full = os.path.join(src, entry)
        if os.path.isdir(full) and entry.endswith("_graphs"):
            shutil.copytree(full, os.path.join(dst, entry), dirs_exist_ok=True)

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert a Parquet dashboard data layout back into JSON."
    )
    parser.add_argument("--src", required=True)
    parser.add_argument("--dst", required=True)
    args = parser.parse_args()
    stats = convert_dir(args.src, args.dst)
    logger.info("Parquet -> JSON conversion complete: {} -> {}", stats, args.dst)


if __name__ == "__main__":
    main()
