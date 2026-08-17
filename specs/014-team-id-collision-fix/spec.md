# Feature Specification: Team ID Collision & Membership Duplication Fix

**Feature Branch**: `014-team-id-collision-fix`

**Created**: 2026-08-16

**Status**: Draft

**Input**: User description: "Fix two compounding data-integrity bugs discovered while investigating a user report that a researcher (Paulo Sérgio Dos Santos Júnior, IFES Campus Serra) appears associated with many unrelated campuses and research groups (e.g. 'Aquicultura e Ambiência Animal' at Itapina campus) that he has no real connection to. Root cause #1 (100% prevalence): research groups and initiatives are provisioned into the same shared teams table using each entity's own domain ID directly as the shared primary key. research_groups.id and initiatives.id are independent numbering sequences that both start at 1, so they collide constantly — verified: ALL 344 research groups (100%) share their numeric ID with some initiative, so every research group's exported member list is contaminated by an unrelated initiative's team. Root cause #2 (compounding): the membership table has no uniqueness constraint, so 'insert or ignore' calls intended to make re-provisioning idempotent silently fail to prevent duplicates — confirmed 14,814 of 62,949 membership rows (23.5%) are exact duplicates from repeated pipeline runs. Goal: research group member lists must only ever reflect that group's real, historical members, never an unrelated initiative's team. Re-running provisioning any number of times must never accumulate duplicate rows. Both fixes must preserve all currently-correct data and must clean up the already-accumulated corruption in the live database, not just prevent it going forward."

## Clarifications

### Session 2026-08-16

- Q: 152 of 11,554 duplicate membership pairs genuinely differ in recorded role (not just incidental metadata) — which copy should survive cleanup? → A: The most recent copy (highest row id / most recent provisioning run) — reflects the most current known state and matches the recency-based tie-break already used elsewhere in this data-quality effort.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Research Group Pages Show Only Real Members (Priority: P1)

As a Dashboard visitor viewing a research group's profile, I need to see only the people who are actually part of that group — never people who happen to belong to a completely unrelated initiative/project that coincidentally shares the same internal identifier — so that the group's member list, campus, and field of research are trustworthy instead of mixing in unrelated people's data.

**Why this priority**: This is the direct, currently-active bug affecting every single research group in the system (100% of the 344 groups have at least one colliding initiative). It's the most visible, highest-trust-impact defect, and it's what the reporting user directly observed.

**Independent Test**: Can be fully tested by picking any research group, listing its exported members, and confirming every listed person has a real, verifiable historical connection to that specific group — none of them are present only because of an initiative that happens to share the group's numeric ID.

**Acceptance Scenarios**:

1. **Given** a research group and an unrelated initiative that happen to share the same internal identifier, **When** the research group's member list is generated, **Then** it contains only that group's real members — none of the initiative's team members appear, unless they are independently also real group members.
2. **Given** a person who is a genuine member of an initiative's team but has no connection to the research group sharing that initiative's identifier, **When** that person's profile is viewed, **Then** their initiative membership is still shown correctly, but they are not listed as a research group member they never belonged to.
3. **Given** the already-affected live data (generated before this fix), **When** the fix is applied, **Then** the incorrect group memberships are removed from the current database — visitors don't have to wait for some future full rebuild to see correct data.

---

### User Story 2 - Re-Running Data Provisioning Never Creates Duplicate Memberships (Priority: P2)

As the person maintaining the weekly data pipeline, I need every re-run of the provisioning/backup-restoration process to leave membership data exactly as accurate as a single run would — never accumulating duplicate entries — so that data quality doesn't silently degrade a little more with every weekly run.

**Why this priority**: This is the systemic safeguard that prevents new corruption (of the ordinary duplication kind, distinct from the ID-collision kind) from continuing to accumulate after this fix ships. It compounds with User Story 1's bug today, making every research group's contamination worse each week, but is scoped as its own concern because it also affects memberships that have nothing to do with the ID collision.

**Independent Test**: Can be fully tested by running the provisioning/backup-restoration process twice in a row against the same source data and confirming the resulting membership counts are identical after the second run (no growth).

**Acceptance Scenarios**:

1. **Given** a database that has already been provisioned once from a given source archive, **When** provisioning is run again from the same source archive, **Then** the total number of membership records does not increase.
2. **Given** the already-accumulated duplicate membership records in the live database, **When** the fix is applied, **Then** the duplicates are removed, leaving exactly one record per real (person, group-or-initiative, role) relationship.

---

### User Story 3 - Verifiable Confirmation That the Corruption Is Gone (Priority: P3)

As a data steward responsible for data quality, I need a way to confirm, after the fix runs, that no research group still shares its identifier with an initiative in a way that mixes their members, and that no duplicate membership records remain — so I can verify the fix worked without having to manually spot-check individual profiles like the one that surfaced this bug.

**Why this priority**: This is a verification/audit capability layered on top of User Stories 1 and 2 — valuable for confirming success and catching any future regression early, but not required for the core data to be correct.

**Independent Test**: Can be fully tested by running the verification check against the live database immediately after the fix and confirming it reports zero remaining cross-contaminated groups and zero duplicate membership records.

**Acceptance Scenarios**:

1. **Given** the fix has been applied, **When** the verification check runs, **Then** it reports the count of research groups still affected by ID collision (expected: zero) and the count of duplicate membership records (expected: zero).

---

### Edge Cases

- A research group and an initiative that share an identifier, where a specific person genuinely belongs to **both** (independently) — that person must still appear as a group member (via their real group membership), not be excluded just because their initiative also shares the group's identifier.
- An initiative whose own team happens to have zero members — must not be treated as an error; it simply contributes no memberships.
- A research group's existing public identifier (used in Dashboard links/URLs) must not change as a side effect of this fix — only the incorrect membership records tied to the collision are removed, not the group's identity itself.
- Two duplicate membership records that differ only in a field unrelated to identity (e.g. recorded role differs between the two copies because of two different source runs) — the cleanup must resolve this deterministically rather than arbitrarily discarding one and keeping the other without a defined rule.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST ensure a research group's exported member list contains only people with a real, direct historical association to that specific group — never members of an initiative/project that merely happens to share the group's internal identifier.
- **FR-002**: The system MUST preserve every person's real initiative-team memberships exactly as they are today — this fix removes incorrect *research group* memberships only, it does not remove or alter correct *initiative* memberships.
- **FR-003**: A research group's public-facing identifier (the one used in Dashboard links and already-published references) MUST remain unchanged by this fix.
- **FR-004**: Re-running the provisioning/backup-restoration process any number of times against unchanged source data MUST produce the same membership record count as a single run — no accumulation of duplicates.
- **FR-005**: The fix MUST correct the already-accumulated corruption (both the cross-contaminated group memberships from ID collisions, and the duplicate membership records from repeated non-idempotent runs) in the current live database and its persistent backup — not only prevent new corruption going forward.
- **FR-006**: The system MUST provide a way to verify, after the fix, that zero research groups remain affected by identifier collision and zero duplicate membership records remain.
- **FR-007**: When cleaning up duplicate membership records that differ in a non-identity field (e.g. recorded role — confirmed to occur in 152 of 11,554 duplicate pairs in the live data), the cleanup MUST keep the most recently created copy (i.e. the one from the most recent provisioning run) and discard the older copy/copies, so repeated cleanup runs produce identical results.

### Key Entities

- **Research Group**: A team-like entity with real historical members, a home campus, and a stable public identifier. Must not be confused with any initiative.
- **Initiative**: A project/initiative with its own team of real participants, tracked independently of research groups even when their internal identifiers coincide.
- **Membership Record**: A record linking one person to one group-or-initiative with a role. Must be unique per (person, group-or-initiative, role) — never duplicated by repeated provisioning runs.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every research group membership that can be positively verified against an available ground-truth source (the canonical archive's snapshot, or a live sync's audit trail) no longer shows a member who is only present due to an identifier collision — confirmed on the live database across all 344 previously-colliding groups. **Known limitation** (see Assumptions): a majority of collision-affected rows (14,811 of ~16,000+) could not be positively classified against either available ground-truth source and were left untouched rather than guessed at, per FR-007's "never guess-delete/reattribute" principle — these represent membership data older than any currently-available archive or audit trail, and closing this gap requires either locating an older/richer source snapshot or accepting a lower-confidence classification rule, which is out of scope for this pass. This was an explicit, informed scope decision (not an oversight) made after directly confirming no richer source data is currently available.
- **SC-002**: 0% of membership records in the live database are duplicates of an existing (person, group-or-initiative, role) relationship (down from 23.5% before the fix) — **fully achieved**, confirmed 0 remaining duplicate groups on the live database after the fix.
- **SC-003**: Running the provisioning/backup-restoration process twice in a row against the same source data results in an identical membership record count after both runs.
- **SC-004**: 100% of previously-correct data (research group identifiers, initiative memberships, and all other researcher/group/initiative fields) remains unchanged and intact after the fix — verified by comparing before/after record counts for everything except the specific corruption being removed.
- **SC-005**: A person known to have a real historical research-group affiliation (verified against source records) continues to show that affiliation after the fix runs.

## Assumptions

- The already-accumulated corruption in the live active database and its persistent backup is safe to correct in place — this is a data-quality fix to existing records, not a change requiring re-collection of any source data (the correct source data already exists in the canonical archives and live sync sources; the bug is in how it gets combined, not in the source data itself).
- "Duplicate" for the purpose of this fix means multiple records asserting the same (person, group-or-initiative, role) relationship — differences in incidental metadata (e.g. recorded start/end dates) between duplicate copies do not make them non-duplicates for cleanup purposes, but FR-007's deterministic survivor rule governs which copy's incidental metadata is kept.
- This fix does not need to change the shape of any exported file the Dashboard consumes — it only changes which records end up in those files, so no downstream Dashboard code changes are required (consistent with how the campus/institutional-filtering and edge-capping fixes earlier in this data-quality effort also stayed backward-compatible with the Dashboard).
- **The migration must be applied to both the active database AND its persistent backup, not just one**: discovered during real-pipeline validation — `merge_backup` pulls missing rows from `data/backup/horizon_backup.db` into `db/horizon.db` by explicit row id on every run. Fixing only the active database left the backup's stale, pre-fix rows in place; the very next `merge_backup` (which `weekly_orchestrator.py` runs both once at the start of every weekly run and again as its own phase) re-inserted them, undoing the fix. Confirmed and corrected by re-applying the migration and syncing the corrected state to both files — after which a real `merge_backup` run merged 0 rows (true idempotency, SC-003 confirmed) and the previously-collision-affected groups stayed fixed.
- **The unique index must live in the base schema, not only in the migration** (root-caused after two real weekly runs): the `ux_team_members_team_person_role` index kept disappearing after every `make weekly-flows`. The cause is not corruption — `make weekly-flows` declares `db-reset` as a prerequisite, which runs `rm -f db/horizon.db` followed by `db/create_db.py` (a full `Base.metadata.create_all`) before every single pipeline run. Any index not part of the ORM schema is therefore recreated-away on every run, and the data comes back via `merge_backup` from the persistent backup file. Fixed by adding the index creation to `db/create_db.py` itself, immediately after `create_all`, so it is part of every freshly-provisioned schema. (This also explains why isolated re-tests of `merge_backup`/`consolidate_duplicates`/`export_canonical` never reproduced the loss — none of them drop the schema; only the `db-reset` prerequisite does.)
- **A third ground-truth source was attempted, corrupted production data, and was REMOVED** (incident, kept here so it is not retried the same way): an older sibling-checkout database (`horizon_etl_p/db/horizon.db`) appeared to offer placements for ~18,600 otherwise-unresolvable rows, and a `apply_third_party_ground_truth()` step was built to use it, restricted to people with exactly one unambiguous membership there. It was applied to production and moved 9,461 rows. **This was wrong.** The step copied `team_id` values directly across databases, but team ids are *not* portable between them — verified after the fact: team 92 is "Grupo de estudo e pesquisa em agroecologia" in the old snapshot but "Grupo de Pesquisa em Alfabetização Científica" in the current one; ids 106, 150, 188 and 344 likewise refer to entirely different teams. Since a person's campus is derived from their research group, this silently relocated thousands of people to unrelated groups and wrong campuses. Symptoms reported from the Dashboard: publication counts dropping to zero under a single-campus filter, students vanishing from listings, and specific people (e.g. a Campus Serra student shown as São Mateus). **Resolution**: the database was rolled back to the last known-good snapshot, the safe migration (dedup + archive/live-sync collision re-attribution) re-applied alone, and the entire third-party code path, its CLI flag, and its tests deleted. **Rule for any future cross-database source**: resolve teams by NAME, never by id, and validate against a scratch copy with a spot-check of affected people's campuses before touching production.
- **Ground-truth coverage is partial, by discovery, not by design**: classification was originally designed around matching by person id against the canonical archive (`data/exports/novo_backup.zip`) and live sync audit trails (`entity_change_logs`). Validation against the real database revealed two compounding gaps: (1) `person_consolidator.py`/`reference_consolidator.py` periodically merge duplicate person records, re-pointing `team_members.person_id` with no queryable id-remapping trail, so matching by id alone left ~86% of rows unclassifiable — resolved by matching on normalized person **name** instead, which is stable across those merges; (2) even after switching to name-based matching, a large majority of rows (338 of 344 previously-colliding groups) reference people who appear in neither the current archive snapshot nor any of several older archive snapshots checked (user-supplied historical exports) nor the live sync audit trail — meaning this data predates every currently-available source. No richer ground-truth source was found after actively searching for one; closing this residual gap is explicitly out of scope for this pass and is documented in SC-001 rather than silently left unmeasured.
