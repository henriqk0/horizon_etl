import json
from pathlib import Path

JSON_REPORT_PATH = Path("data/reports/etl_load_report.json")
MARKDOWN_REPORT_PATH = Path("data/reports/etl_load_report.md")


def _fmt_int(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def _table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def _section_inventory(report: dict) -> str:
    source = report["source_inventory"]
    db = report["db_inventory"]
    rows = [[k, _fmt_int(v)] for k, v in db.items()]
    return "\n".join(
        [
            "## Inventario",
            "",
            f"- Arquivos Lattes: **{_fmt_int(source['lattes_json_files'])}**",
            f"- Arquivos fonte SigPesq: **{_fmt_int(source['sigpesq_source_files'])}**",
            "",
            _table(["Entidade", "Quantidade"], rows),
        ]
    )


def _section_duplicates(report: dict) -> str:
    duplicate_summary = report["duplicate_summary"]
    rows = [[k, _fmt_int(v)] for k, v in duplicate_summary.items()]
    return "\n".join(
        [
            "## Duplicados",
            "",
            _table(["Check", "Quantidade"], rows),
        ]
    )


def _section_health(report: dict) -> str:
    health = report["health_checks"]
    rows = [[k, _fmt_int(v)] for k, v in health.items()]
    return "\n".join(
        [
            "## Saude do Banco",
            "",
            _table(["Check", "Quantidade"], rows),
        ]
    )


def _section_lattes_summary(report: dict) -> str:
    lattes = report["lattes_reconciliation"]
    totals = lattes["totals"]
    rows = []
    for entity in ("projects", "articles", "educations", "advisorships"):
        entity_totals = totals[entity]
        rows.append(
            [
                entity,
                _fmt_int(entity_totals["extracted_unique"]),
                _fmt_int(entity_totals["persisted_unique"]),
                _fmt_int(entity_totals["matched"]),
                _fmt_int(entity_totals["missing_in_db"]),
                _fmt_int(entity_totals["extra_in_db"]),
            ]
        )
    lines = [
        "## Reconciliacao Lattes",
        "",
        f"- Curriculos Lattes: **{_fmt_int(lattes['lattes_files_total'])}**",
        f"- Curriculos resolvidos no banco: **{_fmt_int(lattes['resolved_files'])}**",
        f"- Curriculos nao resolvidos: **{_fmt_int(len(lattes['unresolved_files']))}**",
        "",
        _table(
            [
                "Entidade",
                "Extraido",
                "Persistido",
                "Casado",
                "Faltando no banco",
                "Extras no banco",
            ],
            rows,
        ),
    ]
    if lattes["limitations"]:
        lines.extend(["", "### Limitacoes", ""])
        lines.extend(f"- {item}" for item in lattes["limitations"])
    return "\n".join(lines)


def _section_top_deltas(report: dict, limit: int = 5) -> str:
    files = report["lattes_reconciliation"]["files_with_delta"]
    lines = ["## Principais Deltas por Curriculo", ""]
    for entity in ("projects", "articles", "educations", "advisorships"):
        ranked = sorted(
            files,
            key=lambda item: (
                item[entity]["missing_in_db"],
                item[entity]["extra_in_db"],
            ),
            reverse=True,
        )[:limit]
        lines.append(f"### {entity}")
        lines.append("")
        if not ranked:
            lines.append("- Nenhum delta encontrado.")
            lines.append("")
            continue
        rows = []
        for item in ranked:
            data = item[entity]
            rows.append(
                [
                    item["file"],
                    _fmt_int(data["missing_in_db"]),
                    _fmt_int(data["extra_in_db"]),
                    _fmt_int(data["matched"]),
                    _fmt_int(data["extracted_unique"]),
                    _fmt_int(data["persisted_unique"]),
                ]
            )
        lines.append(
            _table(
                ["Arquivo", "Faltando", "Extra", "Casado", "Extraido", "Persistido"],
                rows,
            )
        )
        lines.append("")
    return "\n".join(lines).rstrip()


def _section_executive_summary(report: dict) -> str:
    duplicates = report["duplicate_summary"]
    health = report["health_checks"]
    totals = report["lattes_reconciliation"]["totals"]
    critical = [
        f"Duplicados estruturais auditados: **{_fmt_int(sum(duplicates.values()))}**",
        f"Artigos faltando na reconciliacao Lattes: **{_fmt_int(totals['articles']['missing_in_db'])}**",
        f"Formacoes faltando na reconciliacao Lattes: **{_fmt_int(totals['educations']['missing_in_db'])}**",
        f"Orientacoes faltando na reconciliacao Lattes: **{_fmt_int(totals['advisorships']['missing_in_db'])}**",
        f"Projetos faltando na reconciliacao Lattes: **{_fmt_int(totals['projects']['missing_in_db'])}**",
        f"Pesquisadores sem resume: **{_fmt_int(health['researchers_without_resume'])}**",
        f"Pesquisadores sem CNPq URL: **{_fmt_int(health['researchers_without_cnpq_url'])}**",
    ]
    return "\n".join(["## Resumo Executivo", ""] + [f"- {item}" for item in critical])


def render_markdown(report: dict) -> str:
    generated_at = report.get("generated_at", "")
    parts = [
        "# Relatorio ETL",
        "",
        f"Gerado em: **{generated_at}**",
        "",
        _section_executive_summary(report),
        "",
        _section_inventory(report),
        "",
        _section_duplicates(report),
        "",
        _section_health(report),
        "",
        _section_lattes_summary(report),
        "",
        _section_top_deltas(report),
        "",
    ]
    return "\n".join(parts).rstrip() + "\n"


def main() -> None:
    report = json.loads(JSON_REPORT_PATH.read_text(encoding="utf-8"))
    markdown = render_markdown(report)
    MARKDOWN_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    MARKDOWN_REPORT_PATH.write_text(markdown, encoding="utf-8")
    print(markdown)


if __name__ == "__main__":
    main()
