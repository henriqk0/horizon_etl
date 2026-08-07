# Quickstart Validation Guide: Student Campus Allocation

**Feature**: [`specs/005-student-campus-allocation/spec.md`](file:///home/rafael/horizon_etl_h/specs/005-student-campus-allocation/spec.md)  
**Branch**: `005-student-campus-allocation`  
**Date**: 2026-08-05

## Validation Scenarios

This guide details how to validate the 3-tier student campus allocation hierarchy and multi-campus resolution end-to-end.

---

### Scenario 1: Unit Test Validation of Resolver Hierarchy

Run pytest targeting the unit tests for `ExportCampusResolver`:

```bash
pytest tests/test_export_campus_resolver.py -k "test_student_campus_hierarchy"
```

**Expected Outcome**:
- Level 1: A student with project campus metadata resolves to `resolved_via: "project"`.
- Level 2: A student with no project links but in a Research Group resolves to `resolved_via: "research_group"`.
- Level 3: A student with no project or group links but with a main advisor resolves to `resolved_via: "main_advisor"`.
- Tie-Breaker: A student with 2 main advisors from different campuses resolves to both campuses in `campuses` array.

---

### Scenario 2: Canonical Export Verification

Run a canonical export and verify `students_canonical.json`:

```bash
make export-canonical CAMPUS=Serra
```

**Verification Steps**:

1. Inspect `output/students_canonical.json`:
   ```bash
   python3 -c "import json; data=json.load(open('output/students_canonical.json')); print('Total students:', len(data)); print('Sample student campus:', data[0].get('campus'), 'resolution:', data[0].get('campus_resolution'))"
   ```

2. Confirm that every student record adheres to [`contracts/students-canonical-export.json`](file:///home/rafael/horizon_etl_h/specs/005-student-campus-allocation/contracts/students-canonical-export.json).
