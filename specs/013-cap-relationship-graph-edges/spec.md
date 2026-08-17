# Feature Specification: Cap Relationship Graph Edges

**Feature Branch**: `013-cap-relationship-graph-edges`

**Created**: 2026-08-16

**Status**: Draft

**Input**: User description: "Cap relationship/collaboration graph edges to prevent unbounded export size and dashboard build OOM. Root cause: the graph generators build an edge for every pair of people who co-occur in the same initiative, research group, or advisorship — a full clique per initiative/group. For groups/initiatives with many members this produces a combinatorial explosion of edges. Confirmed on real exported data: the full people relationship graph is 455MB, the researchers-only relationship graph is 215MB, and the per-research-group relationship graphs total 627MB with individual group files up to 31MB. This makes the downstream Horizon Dashboard fail to build with an out-of-memory error even at a 16GB heap limit, confirmed via a real production build run against a freshly-synced export. Fix: after building each graph, prune every node's edges down to at most its top 3 highest-weight edges (weight = number of relationship evidences: shared initiative + shared research group + advisorship) before exporting. This is a per-node degree cap, not a cap on total node/edge count — the file can still have many edges overall, each still connecting exactly 2 nodes, just far fewer survive per node. Applies uniformly to every relationship and collaboration graph export (both the full/classification-wide graphs and the per-research-group graphs). The exported file shape must not change, since the Dashboard already consumes this exact shape and this fix must stay backward-compatible without requiring Dashboard code changes. Reported statistics alongside each export (node/edge counts, degree distributions, top collaborators, etc.) must be recomputed from the pruned graph, not the original, so they match what's actually in the file."

## Clarifications

### Session 2026-08-16

- Q: If person A's top-3 includes a connection to person B, but B's own top-3 doesn't include A, should the connection still appear in the export? → A: Yes — kept if it's in the top-3 of at least one of the two endpoints (union rule).
- Q: Should the amount of trimming an export performs be visible anywhere, so a silent regression (e.g. trimming stops working) can be detected without opening the files? → A: Yes — each export logs/reports how many edges were removed and the resulting reduction percentage, visible in the weekly run summary.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Dashboard Build Succeeds After a Data Sync (Priority: P1)

As the person responsible for publishing the Horizon Dashboard, I need the site to build successfully every time new ETL data is synced in, so that a routine data refresh doesn't turn into a broken deployment because the underlying data grew too large to process.

**Why this priority**: This is the actively broken state today — the most recent real export already fails the Dashboard's production build with an out-of-memory error, even after raising the memory budget well beyond what the project normally uses. Nothing downstream of this works until it's fixed.

**Independent Test**: Can be fully tested by syncing a freshly generated export into the Dashboard and running its production build to completion without a memory error.

**Acceptance Scenarios**:

1. **Given** a freshly generated data export, **When** the Dashboard is built from it, **Then** the build completes successfully within the memory budget the project already uses for production builds.
2. **Given** a research group or a classification bucket (e.g. researchers, students) with an unusually large number of members, **When** its relationship graph is exported, **Then** the resulting file size stays proportionate to the number of people involved instead of growing quadratically with group size.

---

### User Story 2 - Exports Stay Practical to Generate and Distribute as the Dataset Grows (Priority: P2)

As the person maintaining the weekly data pipeline, I need relationship and collaboration graph exports to stay a manageable size as the number of researchers, groups, and initiatives grows over time, so that the export step doesn't become a recurring source of failures, storage bloat, or slow syncs as the institution's data accumulates.

**Why this priority**: Without a durable bound, the same failure will resurface after the next few data-growth cycles even if today's export is patched by hand. This closes the actual root cause rather than a one-time symptom.

**Independent Test**: Can be fully tested by generating exports from datasets of increasing size (including one with an unusually large group or initiative) and confirming file sizes grow roughly linearly with the number of people, not combinatorially with group/initiative size.

**Acceptance Scenarios**:

1. **Given** a research group whose member count doubles, **When** its relationship graph is regenerated, **Then** the exported file size does not grow anywhere near quadratically with that increase.
2. **Given** the weekly pipeline runs to completion, **When** all relationship and collaboration graph exports are produced, **Then** none of them reach the sizes that previously caused the Dashboard build to fail.

---

### User Story 3 - Graph Statistics Stay Accurate After Trimming (Priority: P3)

As a Dashboard visitor viewing a researcher's or research group's relationship graph and its summary numbers (e.g. top collaborators, connection counts), I need those numbers to describe what's actually shown in the graph, so that the page isn't presenting statistics computed from data that was later discarded.

**Why this priority**: This is a correctness/trust concern layered on top of the P1 fix — once graphs are trimmed, any summary numbers bundled with the export must reflect the trimmed data, or the page would show misleading counts. Lower priority than P1/P2 because it only matters once trimming exists at all.

**Independent Test**: Can be fully tested by generating a trimmed export and confirming every reported count (nodes, edges, per-person degree, top-collaborator lists) matches what a fresh count of the actual exported graph data produces.

**Acceptance Scenarios**:

1. **Given** a trimmed relationship graph export, **When** its bundled statistics are compared against the graph data in the same file, **Then** every count matches exactly.

---

### Edge Cases

- A person with fewer than 3 relationships keeps all of them untrimmed — nothing to cap.
- Two or more relationships tied for the 3rd-strongest spot for a given person: the tie must be broken consistently (deterministically) so re-running the export on unchanged data produces the same result.
- A relationship that is one person's top-3 strongest but not the other person's (their top-3 is filled with stronger connections elsewhere) still appears in the export, per FR-007's union rule — so a person can end up with more than 3 retained connections when others' top-3 choices point back at them.
- A person with zero relationships in the original data (never shared an initiative, group, or advisorship with anyone) should still appear in the export as an isolated node, not be dropped entirely — existing profiles must not disappear from the data.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Every relationship graph export and every collaboration graph export MUST have each person's number of retained connections capped at 3, keeping only that person's 3 strongest connections, ranked by that connection's existing weight value (each graph type already defines its own weight as a count of supporting evidence — e.g. relationship graphs count shared initiatives + shared research groups + advisorships; collaboration graphs count shared initiatives + co-authored articles + advisorships — this feature reuses whichever definition the graph already has, it does not redefine it).
- **FR-002**: The cap MUST apply uniformly across every graph export the pipeline produces today: the full/global graphs, the per-classification graphs (students, researchers, outside-collaborators, unclassified), and the per-research-group graphs.
- **FR-003**: When two or more connections are tied for a person's 3rd-strongest spot, the export MUST resolve the tie the same way every time it is regenerated from the same underlying data.
- **FR-004**: The file format/shape produced for each export MUST remain exactly what it is today — no fields added, removed, or restructured — so the Dashboard continues to read these files without any changes on its side.
- **FR-005**: All statistics bundled alongside each export (total node/edge counts, per-person connection counts, top-collaborator rankings, and any other aggregate figures) MUST be computed from the trimmed data, not the original untrimmed data.
- **FR-006**: A person who ends up with zero retained connections after trimming MUST still appear in the export as a standalone entry — trimming connections must never remove a person from the export entirely.
- **FR-008**: Each export MUST report how many connections were removed by trimming and the resulting size/edge-count reduction, visible in the weekly pipeline's run summary — so a regression in the trimming behavior (e.g. it silently stops running) is visible without having to inspect the export files directly.
- **FR-007**: When person A's top-3 includes a connection to person B, but that same connection is not among person B's own top-3, the connection MUST still be kept in the export — a connection survives trimming if it is in the top-3 of at least one of its two endpoints (union rule). A person may therefore end up with more than 3 retained connections in the final export (when other people's top-3 choices point back at them), but this MUST NOT reintroduce anything close to the original combinatorial blow-up.

### Key Entities

- **Relationship/Collaboration Graph Export**: A file describing people and the connections between them, built from shared initiatives, shared research group membership, and advisorship pairs. Produced in several variants (full population, per-classification subsets, per-research-group subsets).
- **Connection (edge)**: A link between two people, carrying a strength value (weight) equal to how many separate pieces of evidence — shared initiatives, shared groups, advisorships — support that relationship.
- **Person (node)**: An individual represented in a graph export, with a bounded number of retained connections after trimming.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The Dashboard's production build completes successfully from a freshly generated export, using the same memory budget the project already runs its builds with today.
- **SC-002**: The full/global relationship and collaboration graph exports each shrink by at least an order of magnitude in file size compared to the current uncapped exports.
- **SC-003**: No single per-research-group graph export file exceeds a small fraction (under 5%) of its current uncapped size.
- **SC-004**: 100% of the statistics reported inside a trimmed export match an independent recount performed directly against that same file's graph data.
- **SC-005**: Re-generating an export from unchanged underlying data produces byte-for-byte identical trimming results (same edges kept, same ties resolved the same way).
- **SC-006**: Every weekly pipeline run's summary shows, for each graph export, how many connections were removed by trimming and the resulting reduction percentage, without needing to open the export files.

## Assumptions

- "Weight" is already computed today for every connection (shared initiative + shared research group + advisorship evidence) and does not need to be redefined — only used as the ranking basis for trimming.
- The cap of 3 retained connections per person is a fixed number for this feature, not a configurable setting.
- Trimming happens as the very last step before an export is written — every export still starts from the complete underlying relationship data, so the same person's top-3 can differ across different export variants (e.g. their top-3 within their research group's export may differ from their top-3 within the full population export) if the underlying candidate pool differs.
- Downstream consumers (the Dashboard) are not being modified as part of this feature — the fix lives entirely on the data-export side.
