# Data Model & Schema: Student Campus Allocation Hierarchy

**Feature**: [`specs/005-student-campus-allocation/spec.md`](file:///home/rafael/horizon_etl_h/specs/005-student-campus-allocation/spec.md)  
**Branch**: `005-student-campus-allocation`  
**Date**: 2026-08-05

## Canonical Export Schema: `students_canonical.json`

Each student record in `students_canonical.json` includes the following campus fields:

```json
{
  "id": 1042,
  "name": "Maria Silva",
  "classification": "student",
  "classification_confidence": "high",
  "campus": {
    "id": 1,
    "name": "Campus Serra"
  },
  "campuses": [
    {
      "id": 1,
      "name": "Campus Serra"
    },
    {
      "id": 3,
      "name": "Campus Vitória"
    }
  ],
  "campus_resolution": {
    "resolved_via": "project",
    "confidence": "high"
  }
}
```

### Field Definitions

| Field | Type | Description | Nullable |
|---|---|---|---|
| `campus` | `Object \| Null` | Primary resolved campus `{ "id": int, "name": str }` for backward compatibility. | Yes |
| `campuses` | `Array[Object]` | List of all resolved campuses for the student. May contain 0, 1, or multiple campuses. | No (empty array if unallocated) |
| `campus_resolution` | `Object` | Audit provenance of campus resolution. Contains `resolved_via` and `confidence`. | No |

### `campus_resolution.resolved_via` Enum Values

- `"project"`: Resolved at Level 1 via project/edital participation.
- `"research_group"`: Resolved at Level 2 via CNPq Research Group membership.
- `"main_advisor"`: Resolved at Level 3 via main academic advisor campus.
- `"unresolved"`: No campus evidence found at any of the 3 levels.

---

## Resolver Data Structures (`ExportCampusResolver`)

```text
+-----------------------------------------------------------------------+
|                       ExportCampusResolver                            |
+-----------------------------------------------------------------------+
| - _student_level1_project_campuses : dict[person_id, Counter[campus_id]]
| - _student_level2_group_campuses   : dict[person_id, Counter[campus_id]]
| - _student_level3_advisor_campuses : dict[person_id, Counter[campus_id]]
+-----------------------------------------------------------------------+
| + get_student_campuses(person_id) -> list[dict[str, Any]]            |
| + get_student_primary_campus(person_id) -> dict[str, Any] | None       |
| + get_student_resolution_audit(person_id) -> dict[str, Any]           |
+-----------------------------------------------------------------------+
```
