# Quickstart: Validating the Edge Cap Fix

## 1. Unit-level validation (fast, no real data needed)

```bash
cd /home/rafael/horizon_etl_h
source .venv/bin/activate
pytest tests/test_graph_edge_capper.py tests/test_people_relationship_graph_generator.py tests/test_people_collaboration_graph_generator.py -v
```

Confirms: node preservation (FR-006), per-node top-3 + union rule (FR-007), deterministic tie-break (FR-003/SC-005), and that `graph_stats` matches the trimmed graph (FR-005/SC-004).

## 2. Real-data validation (regenerate exports, measure size reduction)

Run against the already-exported canonical JSON files (`data/exports/export.zip`'s contents, or a fresh `data/exports/` from a real pipeline run) — never the live `db/horizon.db` directly for this step, since graph generation only reads the canonical JSON exports, not the database.

```bash
cd /home/rafael/horizon_etl_h
source .venv/bin/activate
python3 -c "
from src.core.logic.people_relationship_graph_generator import PeopleRelationshipGraphGenerator
g = PeopleRelationshipGraphGenerator()
g.generate_all(
    researchers_path='data/exports/researchers_canonical.json',
    initiatives_path='data/exports/initiatives_canonical.json',
    research_groups_path='data/exports/research_groups_canonical.json',
    advisorships_path='data/exports/advisorships_canonical.json',
    output_dir='data/exports',
)
"
du -sh data/exports/people_relationship_graph.json data/exports/research_group_relationship_graphs/
```

**Expected** (per SC-002/SC-003): `people_relationship_graph.json` drops from ~455MB to at most a few tens of MB; `research_group_relationship_graphs/` drops from 627MB total (up to 31MB per file) to well under 5% of that per file.

## 3. End-to-end validation (confirms the actual bug is fixed)

This is the real regression test — it's what originally caught the OOM:

```bash
# 1. Regenerate a full export.zip from the ETL with the fix applied
cd /home/rafael/horizon_etl_h
make weekly-flows   # or the export-only subset, if available

# 2. Sync it into the Dashboard the same way the real sync-etl-data.yml workflow does:
#    additive unzip -o (never rm -rf src/data first — see relatorio.md's earlier
#    lesson about this), then sanitize, then build.
cd /home/rafael/horizon_dashboard_h
unzip -o /home/rafael/horizon_etl_h/data/exports/export.zip -d src/data
node scripts/sanitize-json.mjs src/data
npm run build
```

**Expected** (SC-001): the build completes successfully using the project's existing memory budget (`--max-old-space-size=8192`, already set in `package.json`'s `build` script) — no `--max-old-space-size=16384` override needed, and no `JavaScript heap out of memory` crash.

## 4. Audit signal check (FR-008/SC-006)

While running step 3's `make weekly-flows`, confirm the `people_relationship_graph` phase's captured logs include a trim-summary line for the full graph, each classification graph, and each research-group graph (or at minimum an aggregate summary) — e.g. `removed_edge_count` and `reduction_pct` — following the same log-based visibility pattern as `research_group_exporter.py`'s existing `unresolved_count` warning.
