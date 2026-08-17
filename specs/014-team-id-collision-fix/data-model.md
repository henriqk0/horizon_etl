# Phase 1 Data Model: Team ID Collision & Membership Duplication Fix

This feature does not introduce new canonical domain entities (per Constitution Principle II) — it corrects the id-space mapping of existing entities onto the existing `teams`/`team_members`/`initiative_teams` tables, and adds one schema constraint.

## Existing Entities (relationships being corrected)

### Team (`teams`)
Shared base table for two different owners:
- **Research Group's team**: `teams.id == research_groups.id` (correct — joined-table inheritance, `ResearchGroup(Team)`). **Unchanged by this fix** — group ids are stable (FR-003).
- **Initiative's own team**: today wrongly forced to `teams.id == initiatives.id`. **Fixed to an auto-assigned, disjoint id** (Decision 1). The `initiatives.id` value itself never changes — only the *separate* `teams.id` that represents its team.

### Initiative-Team Link (`initiative_teams`)
Many-to-many: `(initiative_id, team_id)`. Already legitimately holds two kinds of rows:
1. An initiative linked to *its own* team (today: `initiative_id == team_id`; after this fix: `team_id` is the initiative's new disjoint team id).
2. An initiative linked to a *research group's* team (`team_id` is a `research_groups.id`) — a real, pre-existing relationship (3,461 of 8,026 current rows), untouched by this fix.

Distinguishing which kind a given row is: `team_id NOT IN (SELECT id FROM research_groups)` → the initiative's own team; `team_id IN (SELECT id FROM research_groups)` → a link to a sponsoring group. This predicate is reused from the existing `canonical_exporter.py:435` guard (Decision 3).

### Membership Record (`team_members`)
`(id, team_id, person_id, role_id, start_date, end_date)`. **Schema change**: add `UNIQUE(team_id, person_id, role_id)` (Decision 2) via a new index — no column changes, fully backward compatible with every existing reader.

## New Structure: Migration Row Classification

Used only internally by `team_membership_migration.py` (Decision 5) — never persisted as a new table, just the migration's working classification for each `team_members` row currently filed under a colliding `team_id`.

| Classification | Meaning | Action |
|---|---|---|
| `real_group` | `person_id` appears in the archive's `research_groups_canonical.json` members list for this group, or is corroborated by an `entity_change_logs` row with `canonical_entity_type='research_group'` and matching `canonical_entity_id` | Left in place (row is correctly attributed) |
| `real_initiative` | `person_id` appears in the archive's `initiatives_canonical.json` team list for the colliding initiative | `team_id` updated to the initiative's newly-assigned disjoint team id |
| `unresolved` | Matches neither list | Left untouched, logged for manual review — never guess-deleted |

## Validation Rules (from Functional Requirements)

- No `research_groups.id` / `teams.id` value changes (FR-003) — the migration only ever changes a `team_members.team_id` value away from a colliding id, never a `research_groups.id` or the `teams.id` of a research group.
- No real membership is deleted, only deduplicated (exact copies) or re-pointed to the correct team (FR-002, FR-005).
- After migration, `SELECT team_id FROM team_members WHERE team_id IN (SELECT id FROM research_groups) AND team_id IN (SELECT id FROM initiatives)` combined with a check that every such row's `person_id` is a real group member — i.e. the verification query behind SC-001 — must return zero contaminated rows.
- After migration, `SELECT team_id, person_id, role_id, COUNT(*) FROM team_members GROUP BY team_id, person_id, role_id HAVING COUNT(*) > 1` — the verification query behind SC-002 — must return zero rows.
