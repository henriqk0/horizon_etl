import shutil
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger

from src.core.logic.backup_db_provisioner import BackupDatabaseProvisioner
from src.core.ports.backup_merger_port import IBackupDatabaseMerger


class BackupDatabaseMerger(IBackupDatabaseMerger):
    """
    Concrete implementation of IBackupDatabaseMerger using SQLite ATTACH DATABASE
    to execute high-performance, atomic data merges from the reference backup database,
    including full entity relationship graphs.
    """

    def __init__(self, provisioner: Optional[BackupDatabaseProvisioner] = None):
        self.provisioner = provisioner or BackupDatabaseProvisioner()

    def ensure_backup_db(
        self,
        backup_db_path: Path,
        source_archive_path: Optional[Path] = None,
    ) -> bool:
        """
        Ensures the reference backup database exists, auto-provisioning if missing.
        """
        try:
            p = self.provisioner.ensure_backup_database(
                backup_db_path=backup_db_path,
                source_archive=source_archive_path,
            )
            return p.is_file() and p.stat().st_size > 0
        except Exception as e:
            logger.error(
                "Failed to ensure backup database at {}: {}", backup_db_path, e
            )
            return False

    def merge(self, active_db_path: Path, backup_db_path: Path) -> Dict[str, Any]:
        """
        Merges missing entities and relationships from backup_db_path into active_db_path.
        """
        active_path = Path(active_db_path).resolve()
        backup_path = Path(backup_db_path).resolve()

        if not backup_path.is_file():
            logger.warning(
                "Backup database not found at {}. Attempting auto-provisioning...",
                backup_path,
            )
            if not self.ensure_backup_db(backup_path):
                logger.error("Could not provision backup database. Aborting merge.")
                return {"status": "error", "error": "backup_not_found"}

        if not active_path.is_file():
            logger.warning(
                "Active database not found at {}. Initializing with backup copy.",
                active_path,
            )
            active_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(backup_path), str(active_path))
            return {"status": "cloned_from_backup"}

        logger.info(
            "Executing Backup Database Merger: merging {} -> {}",
            backup_path.name,
            active_path.name,
        )

        summary: Dict[str, int] = {}
        tables_to_merge = [
            "roles",
            "organizations",
            "persons",
            "researchers",
            "research_groups",
            "initiatives",
            "articles",
            "advisorships",
            "knowledge_areas",
            "teams",
            "team_members",
            "group_knowledge_areas",
            "researcher_knowledge_areas",
            "initiative_knowledge_areas",
            "article_authors",
            "initiative_persons",
            "initiative_teams",
            "advisorship_members",
        ]

        with sqlite3.connect(str(active_path)) as conn:
            conn.execute(f"ATTACH DATABASE '{str(backup_path)}' AS backup_db")
            cur = conn.cursor()

            # organizational_units is reference/catalog data: the backup
            # database is always authoritative for it (it carries the
            # recovered historical campus catalog), so REPLACE active rows
            # by id instead of only adding missing ones. A plain
            # INSERT OR IGNORE would permanently keep a stale/incorrect
            # campus row already present in the active database (e.g. the
            # previously hardcoded id=1="Serra", which collides with the
            # historically correct id=1="Vila Velha") and the dedup-by-name
            # cleanup below would then delete the correct backup row as the
            # "duplicate" instead of the stale one.
            try:
                cur.execute("SELECT count(*) FROM main.organizational_units")
                ou_before = cur.fetchone()[0]
                cur.execute(
                    "INSERT OR REPLACE INTO main.organizational_units (id, name, description, short_name, organization_id) "
                    "SELECT id, name, description, short_name, organization_id FROM backup_db.organizational_units"
                )
                cur.execute("SELECT count(*) FROM main.organizational_units")
                ou_after = cur.fetchone()[0]
                summary["organizational_units"] = ou_after - ou_before
            except Exception as e:
                logger.warning("Error syncing organizational_units from backup: {}", e)
                summary["organizational_units"] = -1

            # Find common tables in both databases
            cur.execute("SELECT name FROM main.sqlite_master WHERE type='table'")
            main_tables = {row[0] for row in cur.fetchall()}
            cur.execute("SELECT name FROM backup_db.sqlite_master WHERE type='table'")
            backup_tables = {row[0] for row in cur.fetchall()}

            for tbl in tables_to_merge:
                if tbl in main_tables and tbl in backup_tables:
                    try:
                        # Count before
                        cur.execute(f"SELECT count(*) FROM main.{tbl}")
                        count_before = cur.fetchone()[0]

                        # Get columns present in both tables
                        cur.execute(f"PRAGMA main.table_info({tbl})")
                        main_cols = [r[1] for r in cur.fetchall()]
                        cur.execute(f"PRAGMA backup_db.table_info({tbl})")
                        backup_cols = [r[1] for r in cur.fetchall()]

                        common_cols = [c for c in main_cols if c in backup_cols]
                        if common_cols:
                            cols_str = ", ".join(common_cols)
                            cur.execute(
                                f"INSERT OR IGNORE INTO main.{tbl} ({cols_str}) SELECT {cols_str} FROM backup_db.{tbl}"
                            )

                        # Count after
                        cur.execute(f"SELECT count(*) FROM main.{tbl}")
                        count_after = cur.fetchone()[0]
                        merged_diff = count_after - count_before
                        summary[tbl] = merged_diff
                        if merged_diff > 0:
                            logger.info(
                                "Merged {} missing rows into table '{}' (total: {})",
                                merged_diff,
                                tbl,
                                count_after,
                            )
                    except Exception as e:
                        logger.warning("Error merging table '{}': {}", tbl, e)
                        summary[tbl] = -1

            # Backfill teams.organization_id for research groups that already
            # exist in the active database with organization_id still NULL.
            # A plain INSERT OR IGNORE on 'teams' never reaches these rows
            # since they already exist (only missing rows get inserted), so
            # existing research group teams need an explicit, scoped UPDATE
            # from the backup's value. Scoped to research_groups only so
            # initiative teams are never touched.
            try:
                cur.execute(
                    "UPDATE main.teams SET organization_id = ("
                    "  SELECT bt.organization_id FROM backup_db.teams bt WHERE bt.id = main.teams.id"
                    ") WHERE main.teams.id IN (SELECT id FROM main.research_groups) "
                    "AND main.teams.organization_id IS NULL "
                    "AND EXISTS ("
                    "  SELECT 1 FROM backup_db.teams bt WHERE bt.id = main.teams.id AND bt.organization_id IS NOT NULL"
                    ")"
                )
                summary["research_group_organization_id_backfilled"] = cur.rowcount
                if cur.rowcount > 0:
                    logger.info(
                        "Backfilled organization_id for {} research group team(s)",
                        cur.rowcount,
                    )
            except Exception as e:
                logger.warning(
                    "Error backfilling research group organization_id: {}", e
                )

            # Backfill initiatives.parent_id for advisorships that already
            # exist in the active database with parent_id still NULL — same
            # reason as the teams.organization_id backfill above: the
            # INSERT OR IGNORE pass only adds missing rows, so an advisorship
            # already ingested this run (Lattes creates them with no parent,
            # since only SigPesq knows the sponsoring project) never picks up
            # the link the backup holds. Scoped to rows whose parent is also
            # present in the active database, so a parent filtered out of a
            # campus-scoped run is never written as a dangling reference.
            try:
                cur.execute(
                    "UPDATE main.initiatives SET parent_id = ("
                    "  SELECT bi.parent_id FROM backup_db.initiatives bi"
                    "  WHERE bi.id = main.initiatives.id"
                    ") WHERE main.initiatives.parent_id IS NULL "
                    "AND EXISTS ("
                    "  SELECT 1 FROM backup_db.initiatives bi"
                    "  JOIN main.initiatives mp ON mp.id = bi.parent_id"
                    "  WHERE bi.id = main.initiatives.id AND bi.parent_id IS NOT NULL"
                    ")"
                )
                summary["initiative_parent_id_backfilled"] = cur.rowcount
                if cur.rowcount > 0:
                    logger.info(
                        "Backfilled parent_id for {} initiative(s)", cur.rowcount
                    )
            except Exception as e:
                logger.warning("Error backfilling initiative parent_id: {}", e)

            # Final cleanup of any duplicate campus entries in organizational_units
            try:
                cur.execute(
                    "DELETE FROM main.organizational_units WHERE rowid NOT IN (SELECT MIN(rowid) FROM main.organizational_units GROUP BY lower(name))"
                )
            except Exception:
                pass

            conn.commit()
            conn.execute("DETACH DATABASE backup_db")

        logger.info("Backup Database Merge completed successfully: {}", summary)
        return {"status": "success", "merged": summary}

    def sync_backup_from_active(
        self, active_db_path: Path, backup_db_path: Path
    ) -> bool:
        """
        Updates backup_db_path with active_db_path after a 100% successful weekly run.
        """
        active_path = Path(active_db_path).resolve()
        backup_path = Path(backup_db_path).resolve()

        if not active_path.is_file():
            logger.error("Active database not found at {}. Cannot sync.", active_path)
            return False

        try:
            logger.info("Syncing reference backup database from {}...", active_path)
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(active_path), str(backup_path))
            logger.info(
                "Reference backup database successfully updated at {}", backup_path
            )
            return True
        except Exception as e:
            logger.error("Failed to sync backup database: {}", e)
            return False
