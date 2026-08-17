# Phase 0 Research: Team ID Collision & Membership Duplication Fix

No unresolved `NEEDS CLARIFICATION` markers remained in the Technical Context after `/speckit-clarify`. This document records the investigation and design decisions behind the plan.

## Decision 1: Give initiative-linked teams a disjoint id space, don't eliminate them

**Decision**: `backup_db_provisioner.py` currently does, for every initiative:
```python
cur.execute("INSERT OR IGNORE INTO teams (id, name, description) VALUES (?, ?, ?)", (iid, title, desc))
cur.execute("INSERT OR IGNORE INTO initiative_teams (initiative_id, team_id) VALUES (?, ?)", (iid, iid))
```
forcing `teams.id == initiatives.id`. The fix: stop forcing an explicit id for initiative-linked teams. Let SQLite auto-assign the `teams.id` (omit the `id` column from the `INSERT`), then use whatever id SQLite assigns for the `initiative_teams` link. Before inserting, check for an existing self-owned team first (see Decision 3 for the idempotent lookup), so re-running provisioning reuses the same auto-assigned id instead of creating a new team every run.

**Rationale**: `canonical_exporter.py` genuinely depends on initiatives having a `teams` row — `_fetch_person_project_roles` and the advisorship/initiative "team" export (line ~2225) both join through `initiative_teams` to `team_members` to build an initiative's team/role data. Eliminating the initiative-linked team entirely (relying only on `initiative_persons`, a separate table also populated by the provisioner) would break these two existing, working export queries. `research_groups.id == teams.id` must stay exactly as-is (correct joined-table inheritance, and FR-003 requires group ids stay stable) — so the only entity that can move is the initiative side.

**Alternatives considered**:
- *Fixed numeric offset* (e.g. `teams.id = initiatives.id + 1_000_000`): rejected in favor of native auto-increment — an offset is an arbitrary magic number that could itself collide with some future id range, whereas letting SQLite's own `AUTOINCREMENT`-equivalent rowid assignment pick the next free id is guaranteed collision-free by construction (SQLite always picks `max(rowid)+1`, and `teams.id` already reaches 7,976 today from the very initiative rows being fixed, so anything auto-assigned going forward is already safely past every current and near-future `research_groups.id`, which tops out at 344).
- *Drop the initiative-linked team concept entirely*: rejected — breaks two existing export queries (see above).

## Decision 2: Add a real uniqueness constraint on `team_members`

**Decision**: Add a `UNIQUE(team_id, person_id, role_id)` constraint to `team_members` (via a one-time `CREATE UNIQUE INDEX` migration statement, since SQLite doesn't support adding a constraint to an existing table directly — an index-based unique constraint is the standard SQLite equivalent). Once this exists, the three already-present `INSERT OR IGNORE INTO team_members (team_id, person_id, role_id) VALUES (?, ?, ?)` call sites become genuinely idempotent with no further code changes needed — "OR IGNORE" starts doing what it was always meant to do.

**Rationale**: This is the minimal, most robust fix — it makes the *entire class* of "insert or ignore didn't actually ignore" bugs impossible for this table going forward, including any future call site that might be added, not just the three known today. Matches FR-004 exactly (re-running provisioning must never grow the row count).

**Where the index must be created** (learned from real weekly runs, not from the original design): adding it only inside `team_membership_migration.py` is not enough. `make weekly-flows` runs `db-reset` (`rm -f db/horizon.db` + `db/create_db.py`'s full `Base.metadata.create_all`) before every pipeline run, so any index absent from the ORM schema is wiped on every run. The index creation therefore also lives in `db/create_db.py`, right after `create_all` — the migration's copy remains for retrofitting an already-existing database, but the schema-level copy is what makes it durable.

**Alternatives considered**:
- *Check-before-insert in Python* (`SELECT 1 FROM team_members WHERE team_id=? AND person_id=? AND role_id=?` before each `INSERT`): rejected — more code, slower (one extra round-trip per row across tens of thousands of rows), and doesn't protect against a future call site forgetting the check. A schema constraint is enforced unconditionally.
- *`role_id` excluded from the uniqueness key* (unique on `(team_id, person_id)` only): rejected — a person can legitimately hold two different roles on the same team over time in this domain (e.g. promoted from Student to Researcher), and the existing schema already carries `start_date`/`end_date` per row for exactly this reason; over-constraining to `(team_id, person_id)` alone would make a legitimate role change look like a duplicate-insert conflict and silently drop the second role.

## Decision 3: Idempotent initiative-team lookup reuses the existing `NOT IN research_groups` pattern

**Decision**: Before creating a new team for an initiative, look up whether one already exists via:
```sql
SELECT team_id FROM initiative_teams
WHERE initiative_id = ? AND team_id NOT IN (SELECT id FROM research_groups)
LIMIT 1
```

**Rationale**: `initiative_teams` is a genuine many-to-many table — an initiative can already legitimately link to a *research group's* team (e.g. "this project belongs to group X"), confirmed on the live database: 3,461 of 8,026 `initiative_teams` rows have `initiative_id != team_id`, consistent with live CNPq/SigPesq sync linking initiatives to their owning group. The lookup must distinguish "the initiative's own team" from "a research group this initiative happens to also be linked to" — exactly the same ambiguity `canonical_exporter.py`'s `_fetch_person_project_roles` already resolves with its `WHERE it.team_id NOT IN (SELECT id FROM research_groups)` guard (line 435). Reusing the identical predicate keeps the mental model consistent across the codebase instead of inventing a second way to express the same distinction.

## Decision 4: Add the same defensive guard to the research-group member queries (defense in depth)

**Decision**: `canonical_exporter.py` has at least two more queries that join `team_members` by `team_id = research_groups.id` with no exclusion of collision-contaminated rows: `_fetch_person_research_group_roles` (line ~457) and the researcher-enrichment "person_groups_map" query (line ~1244). Once Decision 1 ships, these queries stop being *structurally* contaminated by new data (initiative-teams no longer share an id with any research group), but as defense-in-depth — and to protect against any *other* future bug that assigns a non-`research_groups`-owned `team_members` row under a colliding id — add the same `AND tm.team_id NOT IN (SELECT id FROM initiatives WHERE id NOT IN (SELECT id FROM research_groups))`-style safety, simplified in practice to just trusting `team_id = rg.id` (an inner join already scoped to `research_groups`) now that ids can't collide; no exclusion clause is actually needed once Decision 1 lands, since the join condition `tm.team_id = rg.id` can only match a row that is unambiguously a research group's own team_id post-fix. This decision is recorded to make explicit that these queries were audited and found safe *once Decision 1 ships* — not that they need their own separate patch.

**Rationale**: Auditing every `team_members` consumer against the post-fix data model, rather than assuming only the two symptom-reported queries matter, is consistent with this being a data-integrity fix, not a UI patch.

## Decision 5: Migration strategy for already-corrupted live data — targeted re-attribution, not wipe-and-rebuild

**Decision**: The one-time migration (`team_membership_migration.py`) does NOT truncate and rebuild `team_members` from scratch. Instead:

1. **Deduplicate** (addresses bug #2): for every `(team_id, person_id, role_id)` group with more than one row, delete all but the highest-`id` row (per the clarified FR-007 rule — highest id = most recently inserted = most current known state).
2. **Re-attribute collision rows** (addresses bug #1): for every `team_id` that is both a `research_groups.id` and an `initiatives.id` (the 344 confirmed collisions), determine which of that `team_id`'s `team_members` rows are really initiative-team members mistakenly filed under the group's id:
   - A row is **real-group** if its `person_id` appears in that group's member list in the canonical archive (`research_groups_canonical.json`'s `members` array) OR is corroborated by an `entity_change_logs` entry with `canonical_entity_type='research_group'` and matching `canonical_entity_id` (i.e. verified by a live CNPq sync — see the group-9 example in this investigation, where `Abrahao`/`Déborah`/`Alex Sandro`'s associations are directly traceable this way).
   - Otherwise, if the `person_id` appears in the colliding initiative's `team` array in `initiatives_canonical.json`, it is **real-initiative** — its `team_id` gets updated to the initiative's newly-assigned disjoint team id (found/created via Decision 3's lookup) instead of being deleted, preserving the relationship per FR-002.
   - Any row matching neither list is left untouched and flagged in the migration's log output for manual review (should be rare/zero in practice, but the migration must never guess-delete a relationship it can't positively classify).
3. Both steps run inside a single transaction per collision group, so a failure partway through never leaves a group half-migrated.

**Rationale**: A full wipe-and-rebuild-from-archive was considered but rejected because `team_members` also receives legitimate *live* writes outside the archive-driven provisioner (`strategies/cnpq_sync.py` adds real CNPq group memberships during ordinary weekly runs, verified via `entity_change_logs` — e.g. group #9 received 3 real live-synced memberships in the current session's run, dated after the static archive was captured). Wiping the table would discard that live-verified data. Targeted re-attribution using the archive plus `entity_change_logs` as ground truth corrects exactly the rows proven wrong without touching anything else.

**Alternatives considered**:
- *Wipe and rebuild `team_members` entirely from `novo_backup.zip` + a fresh full re-run of every sync strategy*: rejected — loses live-only data (see above), far slower, and reintroduces risk of hitting the very duplication bug this feature fixes if run before Decision 2's constraint is in place.
- *Delete all contaminated rows outright instead of re-attributing*: rejected — would violate FR-002 (real initiative memberships, like Paulo Sérgio's on initiative #9, must not be lost).
