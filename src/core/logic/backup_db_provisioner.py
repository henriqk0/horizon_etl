import json
import sqlite3
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

# The reference archive (novo_backup.zip) only carries 1 campus row ("Serra")
# because organizational_units had already collapsed by the time it was
# generated. The full 23-campus catalog below is recovered from the last
# canonical export that predates that regression (commit c12a3c8,
# data/exports/canonical_export_20260610_160943.zip) and uses the same IDs
# already referenced by research_groups.campus_id, so no group data needs
# to be migrated to adopt it. See specs/011-research-group-institutional-filtering/research.md.
HISTORICAL_CAMPUS_CATALOG = [
    (1, "Vila Velha"),
    (2, "Vitória"),
    (3, "Itapina"),
    (4, "Colatina"),
    (5, "Alegre"),
    (6, "Serra"),
    (7, "Guarapari"),
    (8, "Venda Nova do Imigrante"),
    (9, "Cachoeiro de Itapemirim"),
    (10, "São Mateus"),
    (11, "Piúma"),
    (12, "Cariacica"),
    (13, "Linhares"),
    (14, "Viana"),
    (15, "Santa Teresa"),
    (16, "Cefor"),
    (17, "Centro-Serrano"),
    (18, "Presidente Kennedy"),
    (19, "Ibatiba"),
    (20, "Nova Venécia"),
    (21, "Aracruz"),
    (22, "Montanha"),
    (23, "Barra de São Francisco"),
]

# Historically, 342 of the 344 research groups belonged to organization_id=1
# ("Instituto Federal do Espirito Santo"). The live archive's
# research_groups_canonical.json carries organization_id=None for every group
# (it was exported from a database where teams.organization_id was already
# NULL), so this default restores the historical affiliation instead of
# perpetuating the gap. See research.md.
DEFAULT_RESEARCH_GROUP_ORGANIZATION_ID = 1


def _find_or_create_initiative_team(
    cur: sqlite3.Cursor,
    initiative_id: Any,
    name: Optional[str],
    description: Optional[str],
) -> int:
    """Idempotent lookup/creation of an initiative's own team id.

    Its id is intentionally NEVER forced to equal `initiative_id` (unlike a
    research group's team, which correctly reuses research_groups.id via
    joined-table inheritance). research_groups.id (1-344) is a numeric
    subset of initiatives.id (1-7962+), so forcing teams.id ==
    initiatives.id collided with every single research group, merging an
    unrelated initiative's team members into that group's member list.
    Letting SQLite auto-assign the id keeps it disjoint by construction. The
    lookup reuses the same "team_id not owned by a research group" predicate
    canonical_exporter.py's _fetch_person_project_roles already relies on,
    so an initiative already linked to its sponsoring research group's team
    is never mistaken for the initiative's own team. See
    specs/014-team-id-collision-fix/research.md, Decisions 1 and 3.
    """
    existing = cur.execute(
        """
        SELECT team_id FROM initiative_teams
        WHERE initiative_id = ?
          AND team_id NOT IN (SELECT id FROM research_groups)
        LIMIT 1
        """,
        (initiative_id,),
    ).fetchone()
    if existing:
        return existing[0]

    cur.execute(
        "INSERT INTO teams (name, description) VALUES (?, ?)",
        (name or f"Initiative {initiative_id}", description),
    )
    new_team_id = cur.lastrowid
    cur.execute(
        "INSERT OR IGNORE INTO initiative_teams (initiative_id, team_id) VALUES (?, ?)",
        (initiative_id, new_team_id),
    )
    return new_team_id


class BackupDatabaseProvisioner:
    """
    Provisions and manages the persistent reference SQLite backup database
    (data/backup/horizon_backup.db) from the consolidated canonical archive (novo_backup.zip),
    including full entity relationship graphs (authors, project teams with real roles, advisorships, memberships).
    """

    DEFAULT_BACKUP_DB_PATH = Path("data/backup/horizon_backup.db")
    DEFAULT_ARCHIVE_PATTERNS = [
        "data/exports/novo_backup.zip",
        "data/exports/export.zip",
        "novo_backup.zip",
        "export.zip",
    ]

    def find_source_archive(
        self, explicit_path: Optional[Path] = None
    ) -> Optional[Path]:
        if explicit_path and explicit_path.is_file():
            return explicit_path

        for p_str in self.DEFAULT_ARCHIVE_PATTERNS:
            p = Path(p_str).resolve()
            if p.is_file() and p.stat().st_size > 0:
                return p
        return None

    def ensure_backup_database(
        self,
        backup_db_path: Optional[Path] = None,
        source_archive: Optional[Path] = None,
        force_rebuild: bool = False,
    ) -> Path:
        target_path = (backup_db_path or self.DEFAULT_BACKUP_DB_PATH).resolve()
        target_path.parent.mkdir(parents=True, exist_ok=True)

        if (
            target_path.is_file()
            and target_path.stat().st_size > 1024
            and not force_rebuild
        ):
            logger.info("Backup database already present at {}", target_path)
            return target_path

        archive_path = self.find_source_archive(source_archive)
        if not archive_path:
            logger.warning(
                "No source export archive found to provision backup database. Starting empty."
            )
            return target_path

        logger.info(
            "Provisioning reference backup database at {} from {}...",
            target_path,
            archive_path.name,
        )

        self._build_database_from_archive(target_path, archive_path)
        logger.info("Backup database successfully provisioned at {}", target_path)
        return target_path

    def _build_database_from_archive(self, db_path: Path, archive_path: Path) -> None:
        if db_path.exists():
            db_path.unlink()

        # Clone schema from db/horizon.db
        schema_sql = ""
        active_db = Path("db/horizon.db").resolve()
        if active_db.is_file():
            with sqlite3.connect(str(active_db)) as src_conn:
                cur = src_conn.cursor()
                cur.execute(
                    "SELECT sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL"
                )
                schema_sql = "\n".join(row[0] + ";" for row in cur.fetchall())

        with sqlite3.connect(str(db_path)) as conn:
            cur = conn.cursor()
            if schema_sql:
                cur.executescript(schema_sql)

            # team_members has no uniqueness constraint of its own, so the
            # "INSERT OR IGNORE" calls below (e.g. section 11b's two loops,
            # which both derive the same initiative-team relationships from
            # two different views of the source archive) can't actually
            # suppress duplicates without one. See
            # specs/014-team-id-collision-fix/research.md, Decision 2.
            cur.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_team_members_team_person_role "
                "ON team_members(team_id, person_id, role_id)"
            )

            with zipfile.ZipFile(archive_path, "r") as zf:
                namelist = zf.namelist()

                def load_json(name: str) -> List[Dict[str, Any]]:
                    if name in namelist:
                        try:
                            return json.loads(zf.read(name).decode("utf-8"))
                        except Exception as e:
                            logger.warning(
                                "Failed to parse {} from {}: {}",
                                name,
                                archive_path.name,
                                e,
                            )
                    return []

                # 1. Organizations
                orgs = load_json("organizations_canonical.json")
                for o in orgs:
                    if isinstance(o, dict) and o.get("name"):
                        cur.execute(
                            "INSERT OR REPLACE INTO organizations (id, name, description, short_name) VALUES (?, ?, ?, ?)",
                            (
                                o.get("id"),
                                o.get("name"),
                                o.get("description"),
                                o.get("short_name"),
                            ),
                        )

                # 2. Organizational Units (Campuses) - seeded from the recovered
                # historical catalog (HISTORICAL_CAMPUS_CATALOG), not from the
                # live archive's campuses_canonical.json, which only carries 1
                # row. IDs match what research_groups.campus_id already
                # references, so no group data needs to change. Deduplicated
                # by name so re-running provisioning never reintroduces
                # duplicate campus rows.
                seen_campus_names = set()
                for cid, cname in HISTORICAL_CAMPUS_CATALOG:
                    if cname.lower() not in seen_campus_names:
                        seen_campus_names.add(cname.lower())
                        cur.execute(
                            "INSERT OR REPLACE INTO organizational_units (id, name, description, short_name, organization_id) VALUES (?, ?, ?, ?, ?)",
                            (cid, cname, None, None, 1),
                        )

                # Any additional campus present in the live archive but not in
                # the historical catalog (e.g. a genuinely new campus) is
                # still picked up, deduplicated by name.
                campuses = load_json("campuses_canonical.json")
                for c in campuses:
                    if isinstance(c, dict) and c.get("name"):
                        cname = c.get("name").strip()
                        if cname.lower() not in seen_campus_names:
                            seen_campus_names.add(cname.lower())
                            cur.execute(
                                "INSERT OR REPLACE INTO organizational_units (id, name, description, short_name, organization_id) VALUES (?, ?, ?, ?, ?)",
                                (
                                    c.get("id"),
                                    cname,
                                    c.get("description"),
                                    c.get("short_name"),
                                    c.get("organization_id") or 1,
                                ),
                            )

                # 3. Roles catalogue (Used by classification algorithm)
                role_map: Dict[str, int] = {}
                roles_to_seed = [
                    (1, "Pesquisador"),
                    (2, "Coordenador"),
                    (3, "Estudante"),
                    (4, "Líder"),
                    (5, "Membro"),
                    (6, "Estudante (Egresso)"),
                    (7, "Pesquisador (Egresso)"),
                    (8, "Coordinator"),
                    (9, "Researcher"),
                    (10, "Student"),
                    (11, "Leader"),
                    (12, "Member"),
                ]
                for rid, rname in roles_to_seed:
                    cur.execute(
                        "INSERT OR REPLACE INTO roles (id, name) VALUES (?, ?)",
                        (rid, rname),
                    )
                    role_map[rname.lower()] = rid

                # 4. Persons & Researchers
                researchers = load_json("researchers_canonical.json")
                for r in researchers:
                    if isinstance(r, dict) and r.get("name"):
                        pid = r.get("id")
                        name = r.get("name")
                        lattes_id = r.get("lattes_id") or r.get("lattesId")
                        cnpq_url = r.get("cnpq_url") or (
                            f"http://lattes.cnpq.br/{lattes_id}" if lattes_id else None
                        )
                        cur.execute(
                            "INSERT OR REPLACE INTO persons (id, name, identification_id) VALUES (?, ?, ?)",
                            (pid, name, lattes_id),
                        )
                        cur.execute(
                            "INSERT OR REPLACE INTO researchers (id, cnpq_url, resume) VALUES (?, ?, ?)",
                            (pid, cnpq_url, r.get("resume") or r.get("biography")),
                        )

                # 5. Students
                students = load_json("students_canonical.json")
                for s in students:
                    if isinstance(s, dict) and s.get("name"):
                        sid = s.get("id")
                        cur.execute(
                            "INSERT OR IGNORE INTO persons (id, name) VALUES (?, ?)",
                            (sid, s.get("name")),
                        )

                # 6. Research Groups
                groups = load_json("research_groups_canonical.json")
                for g in groups:
                    if isinstance(g, dict) and g.get("name"):
                        gid = g.get("id")
                        cnpq_url = g.get("cnpq_url") or g.get("site")
                        campus_id = (
                            (g.get("campus") or {}).get("id") or g.get("campus_id") or 1
                        )
                        # The live archive's organization_id is always null for
                        # research groups (it was exported from an already-broken
                        # database), so fall back to the historically correct
                        # affiliation instead of perpetuating the gap.
                        organization_id = (
                            g.get("organization_id")
                            or DEFAULT_RESEARCH_GROUP_ORGANIZATION_ID
                        )
                        cur.execute(
                            "INSERT OR REPLACE INTO research_groups (id, campus_id, cnpq_url, site) VALUES (?, ?, ?, ?)",
                            (gid, campus_id, cnpq_url, g.get("site")),
                        )
                        cur.execute(
                            "INSERT OR IGNORE INTO teams (id, name, description, organization_id) VALUES (?, ?, ?, ?)",
                            (gid, g.get("name"), g.get("description"), organization_id),
                        )

                # 7. Initiatives (Projects)
                initiatives = load_json("initiatives_canonical.json")
                for init in initiatives:
                    if isinstance(init, dict) and init.get("name"):
                        iid = init.get("id")
                        title = init.get("name")
                        desc = init.get("description")
                        status = init.get("status") or "Concluded"
                        start_date = init.get("start_date")
                        end_date = init.get("end_date")
                        cur.execute(
                            "INSERT OR REPLACE INTO initiatives (id, name, status, description, start_date, end_date, organization_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (iid, title, status, desc, start_date, end_date, 1),
                        )
                        # Create (or reuse) the initiative's own team. Its id
                        # is intentionally NOT forced to equal `iid` — see
                        # _find_or_create_initiative_team's docstring: forcing
                        # teams.id == initiatives.id collided with
                        # teams.id == research_groups.id (research_groups.id
                        # is a numeric subset of initiatives.id), silently
                        # merging an unrelated initiative's team members into
                        # every research group's member list. See
                        # specs/014-team-id-collision-fix/research.md.
                        _find_or_create_initiative_team(cur, iid, title, desc)

                # 7b. Parent initiative links (advisorship -> sponsoring
                # research project). Only SigPesq carries this relationship
                # (Lattes advisorship payloads have no project field at all),
                # so without restoring it here a SigPesq outage silently
                # collapses every advisorship into the exporter's
                # "Sem Projeto Associado" bucket — the reference backup is
                # supposed to protect exactly this kind of loss. Applied as a
                # second pass, after every initiative row exists, so a child
                # listed before its parent still links; parents missing from
                # the archive (possible in a campus-scoped export, where a
                # parent can be filtered out while its child is kept) are
                # skipped rather than written as a dangling reference.
                parent_links_restored = 0
                skipped_parent_links = 0
                for init in initiatives:
                    if not isinstance(init, dict) or init.get("parent_id") is None:
                        continue
                    parent_id = init.get("parent_id")
                    if not cur.execute(
                        "SELECT 1 FROM initiatives WHERE id = ?", (parent_id,)
                    ).fetchone():
                        skipped_parent_links += 1
                        continue
                    cur.execute(
                        "UPDATE initiatives SET parent_id = ? WHERE id = ?",
                        (parent_id, init.get("id")),
                    )
                    parent_links_restored += 1

                logger.info(
                    "Restored {} parent initiative link(s)", parent_links_restored
                )
                if skipped_parent_links:
                    logger.warning(
                        "Skipped {} parent initiative link(s) referencing an "
                        "initiative absent from the archive",
                        skipped_parent_links,
                    )

                # 8. Articles
                articles = load_json("articles_canonical.json")
                for art in articles:
                    if isinstance(art, dict) and art.get("title"):
                        aid = art.get("id")
                        title = art.get("title")
                        doi = art.get("doi")
                        year = art.get("year")
                        raw_type = str(art.get("type") or "JOURNAL").strip().upper()
                        art_type = (
                            "JOURNAL"
                            if "JOURNAL" in raw_type or "PERIODICO" in raw_type
                            else "CONFERENCE_EVENT"
                        )
                        journal = art.get("journal_conference")
                        volume = str(art.get("volume") or "")
                        pages = str(art.get("pages") or "")
                        cur.execute(
                            "INSERT OR REPLACE INTO articles (id, title, doi, year, type, journal_conference, volume, pages) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                            (aid, title, doi, year, art_type, journal, volume, pages),
                        )

                # 9. Advisorships
                #
                # advisorships_canonical.json is a TWO-LEVEL document: every
                # top-level entry is the sponsoring research project (a plain
                # initiative, or the synthetic id-less "Sem Projeto Associado"
                # bucket), and its nested "advisorships" list holds the actual
                # advisorships. Only the nested entries belong in this table.
                # Registering the wrapper id instead made each parent project
                # masquerade as an advisorship while the real ones had no row
                # at all — and since canonical_exporter.export_advisorships
                # starts FROM advisorships JOIN initiatives ON a.id = i.id,
                # those advisorships (and the parent link restored in 7b) were
                # invisible to it, collapsing every export into the
                # "Sem Projeto Associado" bucket whenever SigPesq was down.
                advs = load_json("advisorships_canonical.json")
                for wrapper in advs:
                    if not isinstance(wrapper, dict):
                        continue
                    # None for the synthetic "no sponsoring project" bucket.
                    wrapper_id = wrapper.get("id")
                    for adv in wrapper.get("advisorships", []):
                        if not isinstance(adv, dict) or adv.get("id") is None:
                            continue
                        avid = adv.get("id")
                        adv_type = (
                            adv.get("type")
                            or adv.get("advisorship_type")
                            or "Advisorship"
                        )
                        program = adv.get("program") or adv.get("description")
                        cur.execute(
                            "INSERT OR REPLACE INTO advisorships (id, type, program) VALUES (?, ?, ?)",
                            (avid, adv_type, program),
                        )
                        cur.execute(
                            "INSERT OR IGNORE INTO initiatives (id, name, status, organization_id) VALUES (?, ?, ?, 1)",
                            (
                                avid,
                                adv.get("name") or adv.get("title") or "Advisorship",
                                adv.get("status") or "Concluded",
                            ),
                        )
                        # Second, independent source for the same parent link
                        # 7b restores from initiatives_canonical.json (both
                        # agree today). Guarded so 7b's value always wins and
                        # a parent absent from this archive is never written
                        # as a dangling reference.
                        if wrapper_id is not None:
                            cur.execute(
                                "UPDATE initiatives SET parent_id = ? "
                                "WHERE id = ? AND parent_id IS NULL "
                                "AND EXISTS (SELECT 1 FROM initiatives p WHERE p.id = ?)",
                                (wrapper_id, avid, wrapper_id),
                            )

                # 10. Knowledge Areas
                kas = load_json("knowledge_areas_canonical.json")
                for ka in kas:
                    if isinstance(ka, dict) and ka.get("name"):
                        cur.execute(
                            "INSERT OR REPLACE INTO knowledge_areas (id, name) VALUES (?, ?)",
                            (ka.get("id"), ka.get("name")),
                        )
                known_area_ids = {
                    ka.get("id")
                    for ka in kas
                    if isinstance(ka, dict) and ka.get("id") is not None
                }

                # 11. JUNCTION TABLES / RELATIONSHIPS WITH REAL ROLES
                # 11a. Article Authors
                for r in researchers:
                    pid = r.get("id")
                    for art in r.get("articles", []):
                        if isinstance(art, dict) and art.get("id"):
                            cur.execute(
                                "INSERT OR IGNORE INTO article_authors (article_id, researcher_id) VALUES (?, ?)",
                                (art.get("id"), pid),
                            )

                # 11b. Initiative Team Members with exact project roles (Student, Coordinator, Researcher)
                initiative_team_id_cache: Dict[Any, int] = {}

                def resolve_initiative_team_id(iid: Any) -> int:
                    cached = initiative_team_id_cache.get(iid)
                    if cached is not None:
                        return cached
                    team_id = _find_or_create_initiative_team(cur, iid, None, None)
                    initiative_team_id_cache[iid] = team_id
                    return team_id

                for init in initiatives:
                    iid = init.get("id")
                    for tm in init.get("team", []):
                        if isinstance(tm, dict) and tm.get("person_id"):
                            pid = tm.get("person_id")
                            # Determine role_id
                            roles_list = [
                                str(x).strip().lower() for x in tm.get("roles", [])
                            ]
                            if tm.get("role"):
                                roles_list.append(str(tm["role"]).strip().lower())

                            if any(
                                "student" in r or "estudante" in r or "bolsista" in r
                                for r in roles_list
                            ):
                                role_id = role_map.get("student", 10)
                            elif any("coord" in r for r in roles_list):
                                role_id = role_map.get("coordinator", 8)
                            else:
                                role_id = role_map.get("researcher", 9)

                            cur.execute(
                                "INSERT OR IGNORE INTO team_members (team_id, person_id, role_id) VALUES (?, ?, ?)",
                                (resolve_initiative_team_id(iid), pid, role_id),
                            )
                            cur.execute(
                                "INSERT OR IGNORE INTO initiative_persons (initiative_id, person_id) VALUES (?, ?)",
                                (iid, pid),
                            )

                for r in researchers:
                    pid = r.get("id")
                    for init in r.get("initiatives", []):
                        if isinstance(init, dict) and init.get("id"):
                            iid = init.get("id")
                            role_name = (init.get("role") or "").strip().lower()
                            if "student" in role_name or "estudante" in role_name:
                                role_id = role_map.get("student", 10)
                            elif "coord" in role_name:
                                role_id = role_map.get("coordinator", 8)
                            else:
                                role_id = role_map.get("researcher", 9)

                            cur.execute(
                                "INSERT OR IGNORE INTO team_members (team_id, person_id, role_id) VALUES (?, ?, ?)",
                                (resolve_initiative_team_id(iid), pid, role_id),
                            )
                            cur.execute(
                                "INSERT OR IGNORE INTO initiative_persons (initiative_id, person_id) VALUES (?, ?)",
                                (iid, pid),
                            )

                # 11c. Advisorship Members
                # Keyed by the nested entry's own id, matching section 9: the
                # supervisor/student pair belongs to that one advisorship, not
                # to its sponsoring project. Attributing them to the wrapper id
                # piled every student of a project onto a single row and left
                # the real advisorships with no members.
                for wrapper in advs:
                    if not isinstance(wrapper, dict):
                        continue
                    for adv in wrapper.get("advisorships", []):
                        if not isinstance(adv, dict) or adv.get("id") is None:
                            continue
                        avid = adv.get("id")
                        if adv.get("supervisor_id"):
                            cur.execute(
                                "INSERT OR IGNORE INTO advisorship_members (advisorship_id, person_id, role_name) VALUES (?, ?, ?)",
                                (avid, adv.get("supervisor_id"), "Supervisor"),
                            )
                        if adv.get("person_id"):
                            cur.execute(
                                "INSERT OR IGNORE INTO advisorship_members (advisorship_id, person_id, role_name) VALUES (?, ?, ?)",
                                (avid, adv.get("person_id"), "Student"),
                            )
                for r in researchers:
                    pid = r.get("id")
                    for adv in r.get("advisorships", []):
                        if isinstance(adv, dict) and adv.get("id"):
                            cur.execute(
                                "INSERT OR IGNORE INTO advisorship_members (advisorship_id, person_id, role_name) VALUES (?, ?, ?)",
                                (adv.get("id"), pid, "Supervisor"),
                            )

                # 11d. Research Group Team Members with exact roles (Pesquisador, Estudante, Líder, etc.)
                for g in groups:
                    gid = g.get("id")
                    for tm in g.get("members", []):
                        if isinstance(tm, dict) and tm.get("id"):
                            m_role = (tm.get("role") or "").strip().lower()
                            role_id = role_map.get(
                                m_role, role_map.get("pesquisador", 1)
                            )
                            cur.execute(
                                "INSERT OR IGNORE INTO team_members (team_id, person_id, role_id) VALUES (?, ?, ?)",
                                (gid, tm.get("id"), role_id),
                            )

                # 11e. Knowledge Area Associations (researcher/group/initiative <-> knowledge_areas)
                skipped_knowledge_area_links = 0

                for r in researchers:
                    pid = r.get("id")
                    for ka in r.get("knowledge_areas", []):
                        if isinstance(ka, dict) and ka.get("id") is not None:
                            if ka.get("id") not in known_area_ids:
                                skipped_knowledge_area_links += 1
                                continue
                            cur.execute(
                                "INSERT OR IGNORE INTO researcher_knowledge_areas (researcher_id, area_id) VALUES (?, ?)",
                                (pid, ka.get("id")),
                            )

                for g in groups:
                    gid = g.get("id")
                    for ka in g.get("knowledge_areas", []):
                        if isinstance(ka, dict) and ka.get("id") is not None:
                            if ka.get("id") not in known_area_ids:
                                skipped_knowledge_area_links += 1
                                continue
                            cur.execute(
                                "INSERT OR IGNORE INTO group_knowledge_areas (group_id, area_id) VALUES (?, ?)",
                                (gid, ka.get("id")),
                            )

                for init in initiatives:
                    iid = init.get("id")
                    for ka in init.get("knowledge_areas", []):
                        if isinstance(ka, dict) and ka.get("id") is not None:
                            if ka.get("id") not in known_area_ids:
                                skipped_knowledge_area_links += 1
                                continue
                            cur.execute(
                                "INSERT OR IGNORE INTO initiative_knowledge_areas (initiative_id, area_id) VALUES (?, ?)",
                                (iid, ka.get("id")),
                            )

                if skipped_knowledge_area_links:
                    logger.warning(
                        "Skipped {} knowledge area link(s) referencing an unknown area_id",
                        skipped_knowledge_area_links,
                    )

            conn.commit()
