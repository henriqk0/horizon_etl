# Quickstart: Validating the Team ID Collision & Membership Duplication Fix

## 1. Unit-level validation (fast, synthetic data)

```bash
cd /home/rafael/horizon_etl_h
source .venv/bin/activate
pytest tests/test_team_membership_migration.py tests/test_verify_team_membership_integrity.py tests/test_backup_db_provisioner.py -v
```

Confirms: dedup keeps the highest-id row (FR-007), collision re-attribution never deletes a real relationship (FR-002), research group ids never change (FR-003), re-running provisioning doesn't grow `team_members` (FR-004).

## 2. Dry-run against a SCRATCH COPY of the real database — never touch `db/horizon.db` directly first

```bash
cd /home/rafael/horizon_etl_h
source .venv/bin/activate
cp db/horizon.db /tmp/claude-1000/-home-rafael-horizon-etl-h/fdae4608-b731-45cf-a7d2-2b177b9d46eb/scratchpad/scratch_horizon_014.db
python3 -c "
from src.core.logic.team_membership_migration import migrate_team_membership
report = migrate_team_membership('/tmp/claude-1000/-home-rafael-horizon-etl-h/fdae4608-b731-45cf-a7d2-2b177b9d46eb/scratchpad/scratch_horizon_014.db', dry_run=True)
print(report)
"
```

**Expected**: `duplicates_removed` ≈ 14,814, `collision_groups_found` ≈ 344, `rows_unresolved` should be small/zero (large `rows_unresolved` means the classification logic needs more ground-truth sources before running for real).

## 3. Real run against the scratch copy, then verify

```bash
python3 -c "
from src.core.logic.team_membership_migration import migrate_team_membership
report = migrate_team_membership('/tmp/.../scratch_horizon_014.db', dry_run=False)
print(report)
"
python3 src/scripts/verify_team_membership_integrity.py --db /tmp/.../scratch_horizon_014.db
```

**Expected**: verification script reports 0 remaining collision-contaminated groups and 0 duplicate rows (SC-001, SC-002).

## 4. Spot-check the original bug report

```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('/tmp/.../scratch_horizon_014.db')
c = conn.cursor()
c.execute('''
    SELECT t.name FROM team_members tm
    JOIN teams t ON t.id = tm.team_id
    JOIN research_groups rg ON rg.id = tm.team_id
    WHERE tm.person_id = 456
''')
print('Paulo Sérgio (id=456) research group memberships:', c.fetchall())
"
```

**Expected**: only groups he's a real historical member of — the collision-only groups (Aquicultura e Ambiência Animal, Engenharia Aplicada e Sustentabilidade, Gestão de Políticas Públicas do Esporte) must no longer appear, while his real initiative #9 (ConectaFAPES software project) membership must still be intact via `team_members`/`initiative_teams`.

## 5. Apply to the real database, then re-provision and re-run the pipeline

Only after steps 1–4 pass cleanly:

```bash
cd /home/rafael/horizon_etl_h
python3 app.py migrate_team_membership   # new CLI command, applies to db/horizon.db
python3 src/scripts/verify_team_membership_integrity.py --db db/horizon.db
make weekly-flows   # confirms the fix holds through a real, full pipeline run — re-provisioning must not reintroduce duplicates or collisions
```

**Expected**: the weekly run completes normally (per the already-established baseline from specs 011–013), and re-running `verify_team_membership_integrity.py` afterward still reports zero issues — confirming provisioning is now truly idempotent (SC-003).
