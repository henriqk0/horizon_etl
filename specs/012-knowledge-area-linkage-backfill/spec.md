# Feature Specification: Knowledge Area Linkage Backfill

**Feature Branch**: `012-knowledge-area-linkage-backfill`

**Created**: 2026-08-15

**Status**: Draft

**Input**: User description: "Fix empty knowledge area junction tables so groups, researchers, and initiatives are correctly linked to their knowledge areas. Root cause: the backup database provisioner only inserts the knowledge_areas header table from the canonical archive — it never reads the nested knowledge_areas arrays present in researchers_canonical.json, initiatives_canonical.json, and research_groups_canonical.json to populate group_knowledge_areas, researcher_knowledge_areas, and initiative_knowledge_areas. All three junction tables are 0 rows in both the active and backup databases, while the entity tables (1,530 knowledge areas, 344 groups, 10,089 researchers, 4,692 initiatives) are fully populated, and the linkage data does exist in the source archive. Even if the provisioner is fixed, the backup merger's table list omits researcher_knowledge_areas and initiative_knowledge_areas entirely, so a correctly provisioned backup still wouldn't propagate two of the three tables into the active database. Secondary gaps: existing research groups never get their knowledge area links re-synced after creation, and initiative knowledge-area linking is skipped for records without keyword metadata. There is also no parent/child hierarchy modeled for knowledge areas at all, despite the report referencing a hierarchy review. Goal: knowledge areas must be correctly and completely linked to the researchers, research groups, and initiatives that hold them, both immediately after fixing the current data and durably across future weekly runs and backup merges."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Knowledge Areas Visible on Researcher, Group, and Initiative Pages (Priority: P1)

As a Dashboard visitor viewing a researcher's, research group's, or initiative's profile, I need to see the knowledge areas actually associated with them, so that I can understand their field of expertise and find related work — instead of seeing no knowledge areas at all, which is the current state for every single entity on the Dashboard.

**Why this priority**: This is a complete, 100% failure of a core discovery feature (0 of 1,530 knowledge areas are linked to anything), directly affecting every researcher, group, and initiative profile. It's the most visible and highest-impact gap.

**Independent Test**: Can be fully tested by opening any researcher, research group, or initiative profile known to have a recorded field of expertise and confirming its knowledge areas are displayed.

**Acceptance Scenarios**:

1. **Given** a researcher whose historical record includes one or more knowledge areas, **When** their Dashboard profile is viewed, **Then** those knowledge areas are listed on the profile.
2. **Given** a research group with recorded knowledge areas, **When** its Dashboard profile is viewed, **Then** those knowledge areas are listed.
3. **Given** an initiative with recorded knowledge areas, **When** its Dashboard profile is viewed, **Then** those knowledge areas are listed.
4. **Given** the knowledge areas analytics/mart views on the Dashboard, **When** they are viewed, **Then** they show non-empty, accurate aggregations instead of empty results.

---

### User Story 2 - Knowledge Area Links Survive Weekly Runs and Backup Merges (Priority: P2)

As the system maintaining data continuity across weekly pipeline runs, I need knowledge area associations to be preserved and correctly merged every time the backup database is provisioned or merged into the active database, so that the linkage fixed in User Story 1 doesn't silently disappear again after the next weekly run.

**Why this priority**: Without this, User Story 1's fix would only be a one-time patch that regresses on the very next weekly run — this closes the actual root cause (the provisioner and merger gaps) rather than just the symptom.

**Independent Test**: Can be fully tested by running the backup provisioning and merge process from a database with known knowledge-area associations, and confirming all three linkage tables (for researchers, groups, and initiatives) are non-empty and accurate afterward.

**Acceptance Scenarios**:

1. **Given** a canonical archive containing researcher, group, and initiative records with nested knowledge area associations, **When** the backup database is (re)provisioned from that archive, **Then** all three knowledge-area association tables are populated to match the source data.
2. **Given** a backup database with populated knowledge-area associations for researchers, groups, and initiatives, **When** the backup-to-active merge step runs, **Then** all three association tables are merged into the active database, not just the group-level one.
3. **Given** a full weekly pipeline run from a clean state, **When** the run completes and canonical export runs, **Then** knowledge area associations remain present and accurate in the exported data.

---

### User Story 3 - Knowledge Areas Stay Current for Existing Groups and Keyword-less Initiatives (Priority: P3)

As a research group whose knowledge areas change over time, or an initiative recorded without keyword metadata, I need my knowledge area associations to be kept up to date by the live ingestion pipeline, not just set once at creation or skipped entirely, so that ongoing data stays accurate rather than only newly created records benefiting from correct linkage.

**Why this priority**: This addresses secondary, lower-frequency gaps in the live (non-backup) ingestion path. It matters for long-term data quality but affects a smaller slice of records than the wholesale table-emptiness fixed in User Stories 1 and 2.

**Independent Test**: Can be fully tested by updating an existing research group's recorded knowledge areas and re-running ingestion, then confirming the group's stored associations reflect the update; and by ingesting an initiative without keyword metadata and confirming it still receives applicable knowledge area associations from other available evidence.

**Acceptance Scenarios**:

1. **Given** an existing research group whose knowledge areas change in the source data, **When** the group is re-ingested, **Then** its stored knowledge area associations are updated to match, not left as they were at creation.
2. **Given** an initiative record without keyword metadata but with other indicators of its knowledge area (e.g. linked researchers' or group's areas), **When** it is ingested, **Then** it still receives a reasonable knowledge area association rather than none.

---

### Edge Cases

- What happens when the source archive's nested knowledge area entries reference a knowledge area name/ID that doesn't exist in the `knowledge_areas` header table? The association must be skipped or flagged rather than silently creating a broken reference or crashing the run.
- How does the system handle a researcher, group, or initiative that genuinely has no known knowledge area (true absence of data) versus one where linkage merely failed? The fix must not fabricate associations for records that legitimately have none.
- When a researcher/group/initiative already has knowledge area associations in the active database that differ from the backup's, the merge unions both sets rather than having one source take precedence — consistent with the additive, non-destructive merge pattern already used for other junction tables in this system (e.g. `article_authors`, `team_members`).
- How should the system behave if the same underlying knowledge area appears under slightly different name variants (e.g. differing capitalization or accents) in different source records — should these be treated as one knowledge area or flagged as a naming inconsistency?
- Introducing a parent/child knowledge-area hierarchy (e.g. a CNPq-style broad area → sub-area structure) is explicitly out of scope for this fix. This spec restores flat entity-to-knowledge-area linkage only; a hierarchy, if needed, is a separate future effort.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST associate each researcher with their recorded knowledge area(s) wherever that data exists in source records.
- **FR-002**: The system MUST associate each research group with its recorded knowledge area(s) wherever that data exists in source records.
- **FR-003**: The system MUST associate each initiative with its recorded knowledge area(s) wherever that data exists in source records.
- **FR-004**: The backup database provisioning process MUST read and populate knowledge area associations for researchers, groups, and initiatives from the canonical archive, not only the knowledge area entity list itself.
- **FR-005**: The backup-to-active database merge process MUST propagate knowledge area associations for all three entity types (researchers, groups, initiatives), not a subset, and MUST union associations additively when the same entity has differing associations in the active and backup databases rather than having either source overwrite the other.
- **FR-006**: Knowledge area analytics/mart exports MUST reflect the true, non-empty set of associations once linkage is restored.
- **FR-007**: The system MUST NOT fabricate a knowledge area association for a researcher, group, or initiative that has no genuine knowledge area evidence in its source data.
- **FR-008**: The system MUST NOT silently drop a knowledge area association whose referenced knowledge area cannot be matched to an existing catalog entry — it MUST be skipped with the omission recorded, or flagged, rather than causing an unexplained data gap.
- **FR-009**: The live (non-backup) ingestion pipeline MUST update a research group's knowledge area associations when the group's recorded knowledge areas change on re-ingestion, not only at initial creation.
- **FR-010**: The live ingestion pipeline MUST derive knowledge area associations for initiatives using available evidence beyond keyword metadata alone, so initiatives lacking keywords are not unconditionally excluded from linkage.
- **FR-011**: Every weekly pipeline run MUST result in knowledge area associations that are present and verifiable for entities known to have them, confirming the fix is durable across runs rather than a one-time correction.

### Key Entities

- **Knowledge Area**: A field-of-expertise classification (e.g. a research domain or sub-domain); 1,530 currently exist as standalone records with zero associations to any other entity.
- **Researcher ↔ Knowledge Area Association**: The link between a researcher and their field(s) of expertise; currently entirely absent (0 rows).
- **Research Group ↔ Knowledge Area Association**: The link between a research group and its field(s) of focus; currently entirely absent (0 rows) despite being the one table already included in the merge process.
- **Initiative ↔ Knowledge Area Association**: The link between an initiative (e.g. project) and its field(s) of focus; currently entirely absent (0 rows) and also omitted from the merge process's table list.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The count of populated researcher-to-knowledge-area associations rises from 0 to a number consistent with the linkage data present in source records.
- **SC-002**: The count of populated research-group-to-knowledge-area associations rises from 0 to a number consistent with the linkage data present in source records.
- **SC-003**: The count of populated initiative-to-knowledge-area associations rises from 0 to a number consistent with the linkage data present in source records.
- **SC-004**: Knowledge area analytics/mart exports that are currently empty contain accurate, non-empty results after the fix.
- **SC-005**: After two consecutive full weekly pipeline runs (including a fresh backup provision and merge), all three association counts remain stable or grow, with zero regressions back to empty tables.
- **SC-006**: Zero knowledge area associations exist in the exported data that cannot be traced to genuine source evidence (no fabricated associations).

## Assumptions

- The nested knowledge area data already present in the canonical archive (`researchers_canonical.json`, `initiatives_canonical.json`, `research_groups_canonical.json`) is accurate and complete enough to serve as the source of truth for backfilling associations; this spec assumes no additional external data source is required for User Stories 1 and 2.
- The existing `knowledge_areas` entity catalog (1,530 rows) is itself correct and does not require modification as part of this fix — only the associations to other entities are missing.
- Introducing a formal parent/child hierarchy for knowledge areas is out of scope for this fix (confirmed); this spec restores flat linkage only.
- "Correctly linked" means the association matches what is recorded in the available source data, not a judgment call about whether that source data is itself optimal or complete.
- This spec addresses knowledge-area linkage specifically; it does not cover unrelated research-group concerns such as institutional/campus attribution (tracked separately in feature 011).
