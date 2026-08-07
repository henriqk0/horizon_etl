# Feature Specification: Student Campus Allocation Hierarchy

**Feature Branch**: `005-student-campus-allocation`

**Created**: 2026-08-05

**Status**: Draft

**Input**: User description: "mude o sistema que define de qual campos o aluno faz parte, coloqe para que siga a a seguinte logica, sera primeiro visto quais projetos esse aluno fez parte e de quais campus foram esses projetos/editais , caso nao seja identificado sera visto quais grupos de pesquisa esse aluno faça parte, e usara o campus desse grupo caso ainda nao seja definido o campus sera pego o campos do seu orientador principal, podendo em caso de empate (mais de 1 orientador de campos diferentes), sera possivel com que o aluno tenha 2 campus"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Priority 1: Project-Based Campus Allocation (Priority: P1)

As a data analyst or manager, I want students who participate in research or extension projects (editais) to be allocated to the campus of those projects, so that students are accurately associated with their active project locations.

**Why this priority**: Projects/editais represent the most direct and active institutional engagement of a student, capturing students who are not registered in formal CNPq research groups.

**Independent Test**: Can be tested by providing student records linked to projects with defined campuses (and no research group memberships), verifying that the student is allocated to the project's campus.

**Acceptance Scenarios**:

1. **Given** a student participating in one or more projects associated with Campus A, **When** campus resolution is executed, **Then** the student is allocated to Campus A based on project evidence.
2. **Given** a student participating in projects from two different campuses (Campus A and Campus B), **When** campus resolution is executed, **Then** the student is allocated to both Campus A and Campus B (multi-campus allocation) or assigned a primary campus with secondary campus listed.

---

### User Story 2 - Research Group Fallback Allocation (Priority: P2)

As a data analyst, I want students who have no project-level campus evidence to inherit their campus from the Research Groups they belong to, so that students without project records remain accurately allocated via CNPq group memberships.

**Why this priority**: Ensures backward compatibility and coverage for students participating in CNPq research groups when direct project location data is absent.

**Independent Test**: Can be tested by providing a student with no project campus links but enrolled in a Research Group tied to Campus B, verifying that the student is allocated to Campus B.

**Acceptance Scenarios**:

1. **Given** a student with no project campus links who is a member of a Research Group linked to Campus B, **When** campus resolution is executed, **Then** the student is allocated to Campus B via Research Group fallback.
2. **Given** a student enrolled in Research Groups across multiple campuses without project campus links, **When** campus resolution is executed, **Then** all matching group campuses are associated with the student.

---

### User Story 3 - Main Advisor Fallback & Multi-Campus Tie-Breaking (Priority: P3)

As a data analyst, I want students who have neither project nor research group campus links to inherit the campus of their main academic advisor(s), allowing multi-campus allocation in case of advisor ties.

**Why this priority**: Serves as the final institutional fallback, preventing students with registered advisorships from remaining unallocated (`campus: null`).

**Independent Test**: Can be tested by providing a student with only an academic advisorship record linked to an advisor from Campus C, verifying that the student is allocated to Campus C.

**Acceptance Scenarios**:

1. **Given** a student with no project or group campus evidence, who is advised by a main advisor from Campus C, **When** campus resolution is executed, **Then** the student is allocated to Campus C via main advisor fallback.
2. **Given** a student advised by two main advisors associated with different campuses (Campus C and Campus D), **When** campus resolution is executed, **Then** the student is allocated to both Campus C and Campus D simultaneously.

---

### Edge Cases

- What happens when a student has no projects, no research group memberships, and no advisor campus information? The student remains unallocated (`campus: null`) with explicit audit logs noting the lack of all three signals.
- What happens when a project has multiple associated campuses? The student inherits all distinct campuses associated with that project.
- How does the system handle students with multiple main advisors versus co-advisors? The fallback prioritizes main advisors (supervisors/orientadores principais); co-advisors are consulted only if main advisor campus data is inconclusive.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST implement a 3-tier cascading priority hierarchy for student campus resolution: (1) Project/Edital Campuses $\rightarrow$ (2) Research Group Campuses $\rightarrow$ (3) Main Academic Advisor Campuses.
- **FR-002**: System MUST evaluate project/edital participation first. If one or more project campuses are identified for a student, campus resolution for that student MUST complete at Level 1 without falling back to group or advisor levels.
- **FR-003**: System MUST evaluate Research Group memberships if and only if no project campuses were identified for the student (Level 2 fallback).
- **FR-004**: System MUST evaluate main academic advisor campuses if and only if neither project nor research group campuses were identified for the student (Level 3 fallback).
- **FR-005**: System MUST support multi-campus allocation for a student when evidence at the winning priority level indicates association with multiple campuses (including ties between main advisors from different campuses).
- **FR-006**: System MUST export both a primary campus representation (for single-campus compatibility views) and a multi-campus list representation in canonical JSON exports (`students_canonical.json`).
- **FR-007**: System MUST log the resolution path and confidence level for each student (e.g., `resolved_via: project`, `resolved_via: research_group`, `resolved_via: main_advisor`, or `unresolved`) for data auditing.

### Key Entities

- **Student (`Person`)**: A canonical person entity classified as a student, now associated with one or more campuses derived via the cascading resolution rules.
- **Campus**: An institutional campus entity (ID, name) linked to projects, research groups, or advisors.
- **Initiative (Project/Edital)**: Research or extension project entity through which Level 1 campus resolution is evaluated.
- **Research Group**: CNPq/institutional research group entity through which Level 2 campus resolution is evaluated.
- **Advisorship (`Advisorship`)**: Academic supervision record linking a student to main advisor(s) for Level 3 campus resolution.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Unallocated student records (`campus: null`) are reduced by at least 40% in canonical exports compared to the legacy single-source (research group only) resolution logic.
- **SC-002**: 100% of students participating in projects with valid campus metadata are allocated to their project campus(es) without falling back to group or advisor levels.
- **SC-003**: 100% of tie scenarios involving multiple main advisors from different campuses result in valid multi-campus allocations without data loss or pipeline crashes.
- **SC-004**: Canonical export pipeline processing time increases by no more than 10% when computing the 3-tier cascading resolution.

## Assumptions

- Project/Edital records (`initiatives`) contain or can be mapped to campus metadata from source systems (SigPesq, editais).
- Main advisors are distinguishable from co-advisors based on advisorship role definitions (`Supervisor`, `Orientador Principal`).
- In multi-campus allocations, the primary campus field will hold the first/most frequent campus while a `campuses` array contains all resolved campuses for backward compatibility with downstream consumers.
