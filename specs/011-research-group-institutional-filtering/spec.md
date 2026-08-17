# Feature Specification: Research Group Institutional Filtering

**Feature Branch**: `011-research-group-institutional-filtering`

**Created**: 2026-08-15

**Status**: Draft

**Input**: User description: "Fix extraneous/orphaned research groups on the Dashboard. Root cause: research_groups.campus_id references 23 distinct campus IDs but organizational_units currently has only 1 row (Serra) after a prior dedup fix collapsed the table — 315 of 344 groups (91.6%) have a campus_id that doesn't resolve to any real organizational_units row. Instead of excluding these unresolved groups, src/core/logic/research_group_exporter.py silently reassigns them to whatever campus is first in the map (masking the problem). Additionally, teams.organization_id is NULL for all 344 groups, and the exporter fabricates a fallback organization name for display. The weekly export also runs with no institutional/campus scope (campus_name=None), so nothing is filtered. Goal: research groups exported to the Dashboard should only include groups with a valid, resolvable institutional affiliation (campus and organization). Orphaned/unresolvable groups must not be silently relabeled — they should either be excluded from canonical export or explicitly flagged as unresolved so the Dashboard can filter/report them separately. This also requires restoring the correct campus catalog (the ~20+ real IFES campuses) into organizational_units and backfilling research_groups.campus_id to the correct historical campus rather than leaving it dangling."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Trustworthy Campus Attribution on the Dashboard (Priority: P1)

As a Dashboard visitor filtering research groups by campus, I need every listed group to show its real, correct campus so that the campus filter and group listings are trustworthy, instead of dozens of unrelated groups being mislabeled as belonging to a single campus (currently "Serra") that isn't actually their home campus.

**Why this priority**: This is the direct cause of the reported bug ("Triple Campus Serra"-style mislabeling extended to hundreds of groups). Without accurate attribution, every downstream use of campus data (filters, counts, institutional reporting) is wrong, and it's the most visible, highest-trust-impact defect.

**Independent Test**: Can be fully tested by running a canonical export after the campus catalog is restored and observing that groups display their historically correct campus rather than all collapsing to one campus.

**Acceptance Scenarios**:

1. **Given** a research group whose historical campus is "Vitória", **When** the canonical export runs, **Then** the exported group record shows "Vitória" as its campus, not "Serra" or any other unrelated campus.
2. **Given** the Dashboard's campus filter dropdown, **When** a user opens it, **Then** it lists each real IFES campus that has at least one attributed group, with accurate group counts per campus.
3. **Given** a research group with a `campus_id` that still cannot be resolved to any known campus after the catalog is restored, **When** the canonical export runs, **Then** the group is either excluded from the export or clearly flagged as having an unresolved campus — it is never silently relabeled as a different, unrelated campus.

---

### User Story 2 - Institutional Scope Validation Before Export (Priority: P2)

As a data steward responsible for the Dashboard's data quality, I need the weekly export to validate that every research group has a resolvable institutional affiliation (campus and parent organization) before it is published, so that groups with broken or missing institutional links don't reach the public Dashboard unnoticed.

**Why this priority**: This is the systemic safeguard that prevents the User Story 1 problem from recurring after any future data merge or scrape. It's slightly lower priority than the immediate visible fix because it is a preventative/process control rather than a user-facing symptom.

**Independent Test**: Can be fully tested by intentionally introducing a group with a dangling `campus_id` or null `organization_id` into the working database and confirming the export process flags or excludes it rather than fabricating a valid-looking value.

**Acceptance Scenarios**:

1. **Given** a research group with no valid parent organization link, **When** the export/validation step runs, **Then** the group is reported as having an unresolved organizational affiliation rather than being assigned a fabricated organization name.
2. **Given** a weekly export run completes, **When** a data steward reviews the run's summary, **Then** they can see a count of groups excluded or flagged for unresolved institutional affiliation, so silent data quality regressions are visible instead of hidden.

---

### User Story 3 - Complete, Accurate Campus Catalog (Priority: P3)

As the system maintaining institutional reference data, I need the full historical set of real IFES campuses present in the reference catalog, so that groups scraped or merged from any campus can be correctly attributed rather than only the one campus that happens to remain after prior cleanup.

**Why this priority**: This is a foundational data-restoration task that User Stories 1 and 2 depend on, but on its own it delivers no visible improvement to the Dashboard until attribution and validation are also in place — hence it's sequenced as supporting infrastructure rather than the top-priority user-facing fix.

**Independent Test**: Can be fully tested by querying the reference campus catalog after the fix and confirming it contains the full expected set of real campuses (not just one), each with a stable, unique identifier.

**Acceptance Scenarios**:

1. **Given** the reference campus catalog after restoration, **When** it is inspected, **Then** it contains one row per real, distinct IFES campus with no duplicates and no fabricated/placeholder entries.
2. **Given** a research group previously pointing to a now-missing campus, **When** the catalog is restored and IDs are backfilled, **Then** the group points to its correct historical campus rather than an arbitrary or default one.

---

### Edge Cases

- What happens when a research group's historical campus cannot be determined from any available source (scraper archive, backup, or naming convention)? It must be flagged as unresolved, never defaulted to an arbitrary campus.
- How does the system handle a campus name that has legitimate near-duplicate spellings (e.g. accented vs. unaccented, or abbreviation vs. full name) during catalog restoration, to avoid recreating the earlier "Triple Campus Serra" duplication bug?
- A group whose `organization_id` is null but whose campus is resolvable is still considered unresolved: both a valid campus and a valid parent organization are required for a group to be treated as fully resolved and exported normally (see FR-005).
- How should previously-published groups that become "unresolved" under the new validation (i.e., groups currently visible on the Dashboard today) be handled during rollout — immediately removed, or held with a grace/warning period?
- What happens when two research groups have the same name but different (now-corrected) campuses — are they genuinely distinct groups, or is this evidence of a further amalgamation/duplication problem?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST maintain a reference catalog of institutional campuses that includes every real, distinct campus historically observed in source data, not merely a single default entry.
- **FR-002**: The system MUST NOT contain duplicate entries for the same real-world campus in the reference catalog (preserving the intent of the earlier "Triple Campus Serra" deduplication fix).
- **FR-003**: Each research group MUST be attributed to its correct, historically accurate campus, restored from source/backup data where the current attribution is broken.
- **FR-004**: The system MUST NOT reassign a research group to a campus other than its own resolvable campus for display purposes; when a group's campus cannot be resolved, the system MUST treat it as unresolved rather than substituting an unrelated campus.
- **FR-005**: The canonical export process MUST exclude or explicitly flag research groups whose institutional affiliation cannot be fully resolved — a group is considered resolved only when it has both a valid, resolvable campus AND a valid, resolvable parent organization; missing either is sufficient to exclude/flag it.
- **FR-006**: The system MUST NOT fabricate a placeholder or default organization name for a research group whose parent organization link is missing; such groups must be flagged as unresolved instead.
- **FR-007**: The weekly export process MUST apply institutional scope validation by default, rather than exporting all groups unfiltered regardless of institutional affiliation.
- **FR-008**: The system MUST report, for each export run, how many research groups were excluded or flagged due to unresolved institutional affiliation, so data quality issues remain visible rather than silent.
- **FR-009**: The Dashboard's campus filter MUST reflect only real, resolved campuses and accurate per-campus group counts.
- **FR-010**: The system MUST preserve the historical identity (name and known attributes) of each research group while correcting its institutional attribution — correcting campus/organization links must not alter unrelated group data.

### Key Entities

- **Research Group**: A team/lab entity with a name and (after this fix) a resolvable link to exactly one campus and one parent organization; previously many groups had broken or fabricated institutional links.
- **Campus (Organizational Unit)**: A real, distinct institutional location (e.g. a specific IFES campus); the reference catalog must contain the complete, deduplicated set rather than a single collapsed entry.
- **Organization**: The parent institution a research group and its campus belong to; currently unset for all research groups and must be correctly linked or the group flagged as unresolved.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The proportion of research groups with an unresolved (dangling or missing) campus attribution drops from 91.6% to 0% for groups whose historical campus can be determined from available data.
- **SC-002**: 100% of research groups shown on the Dashboard display a campus that is a real, distinct institutional location — no group is mislabeled with a campus other than its own.
- **SC-003**: The reference campus catalog contains no duplicate entries for the same real-world campus, verified by a single canonical row per campus name.
- **SC-004**: Every weekly export run produces a visible count of groups excluded or flagged for unresolved institutional affiliation, reviewable by a data steward without inspecting raw database tables.
- **SC-005**: Zero research groups appear on the Dashboard with a fabricated or placeholder organization name; groups without a resolvable organization are excluded or clearly flagged instead.

## Assumptions

- The correct historical campus for each research group can be recovered from existing source data (the original scraper archives, the backup database's pre-collapse state, or naming/metadata already present on the group records); this spec assumes recovery is possible for the large majority of the 315 currently-orphaned groups, with the Edge Cases section covering the remainder.
- "Institutional affiliation" for a research group consists of two parts — campus and parent organization — consistent with the existing data model (`campus_id`, `organization_id`); this spec does not introduce new institutional concepts beyond what already exists in the schema.
- The single remaining campus ("Serra") is itself a legitimate, correctly-deduplicated entry and does not need to be re-validated as part of this fix, only supplemented with the missing campuses.
- Existing groups that currently display incorrect campus attribution are considered a data quality defect to be corrected, not intentional data — this spec assumes there is no case where the current single-campus attribution is actually desired behavior.
- This spec addresses institutional attribution correctness and export-time validation; it does not cover unrelated research-group concerns such as membership rosters, publication counts, or knowledge-area linkage (tracked separately).
