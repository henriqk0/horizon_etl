# Phase 0 Research: Student Campus Allocation Hierarchy

**Feature**: [`specs/005-student-campus-allocation/spec.md`](file:///home/rafael/horizon_etl_h/specs/005-student-campus-allocation/spec.md)  
**Branch**: `005-student-campus-allocation`  
**Date**: 2026-08-05

## Research Topics & Decisions

### 1. Cascading 3-Tier Resolution Strategy in `ExportCampusResolver`

- **Decision**: Implement a sequential priority evaluation for student entities (`"researcher"` classified as `"student"`):
  1. **Level 1 (Projects/Editais)**: Query student participation in initiatives (`initiatives` / `initiative_teams`) that have associated campus metadata or research group teams with campuses.
  2. **Level 2 (Research Groups)**: If no project campuses are found, query student membership in CNPq Research Groups (`team_members` $\rightarrow$ `research_groups`).
  3. **Level 3 (Main Advisor)**: If neither project nor group campuses are found, query student advisorships (`advisorships`) to locate main academic advisors (`Supervisor` / `Orientador`) and inherit their primary campus.
- **Rationale**: Strict 3-tier cascade guarantees that active project participation takes precedence over group membership, which in turn takes precedence over academic supervision.
- **Alternatives Considered**:
  - *Weighted Sum across all levels simultaneously*: Rejected because project location reflects explicit active edital participation and should strictly override passive group affiliation.

### 2. Multi-Campus Payload Schema & Backward Compatibility

- **Decision**: Update canonical student exports (`students_canonical.json`) to include:
  - `"campus"`: Primary campus dictionary `{ "id": 1, "name": "Campus Serra" }` (or `null`) for backward compatibility with existing dashboard consumers.
  - `"campuses"`: List of all resolved campus dictionaries `[ { "id": 1, "name": "Campus Serra" }, { "id": 2, "name": "Campus Vitória" } ]`.
  - `"campus_resolution"`: Provenance metadata `{ "resolved_via": "project" | "research_group" | "main_advisor" | "unresolved", "confidence": "high" | "medium" | "low" }`.
- **Rationale**: Preserves contract compatibility with existing dashboard components expecting a single `"campus"` object while enabling multi-campus visualization in graph/analytics modules.
- **Alternatives Considered**:
  - *Replacing `"campus"` with `"campuses"`*: Rejected because it would break existing dashboard components that dereference `student.campus.name`.

### 3. Main Advisor Identification & Multi-Advisor Tie-Breaking

- **Decision**:
  - Main advisors are identified from `advisorships` where `role_name` matches primary supervisor roles (`"Supervisor"`, `"Orientador"`, `"Main Advisor"`).
  - If a student has multiple main advisors with different campuses, all advisor campuses are recorded in the Level 3 resolution step, resulting in a multi-campus allocation (`len(campuses) > 1`).
  - Deserialization tie-breaker for single `"campus"` field: In case of equal weight between 2 campuses, sort deterministically by `(campus_name, campus_id)`.
- **Rationale**: Ensures deterministic, repeatable exports while fully capturing multi-campus mentorship networks.
