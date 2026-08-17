# Implementation Plan: Research Group Institutional Filtering

**Branch**: `011-research-group-institutional-filtering` | **Date**: 2026-08-15 | **Spec**: [specs/011-research-group-institutional-filtering/spec.md](spec.md)

**Input**: Feature specification from `specs/011-research-group-institutional-filtering/spec.md`

## Summary

Restaurar o catálogo completo de campi (`organizational_units`, 23 registros reais) e de organizações (`organizations`) a partir do export canônico histórico anterior à regressão (`canonical_export_20260610_160943.zip`, recuperável via `git show c12a3c8:...`), realinhando-o com os `campus_id` já presentes em `research_groups` — sem necessidade de migrar dados nos próprios grupos, já que os IDs históricos e os atuais coincidem. Em seguida, substituir a lógica de fallback em `research_group_exporter.py` (que hoje reatribui silenciosamente qualquer grupo não resolvido a um campus/organização arbitrário) por exclusão/flag explícita de grupos sem afiliação institucional completa (campus **e** organização), e tornar essa validação parte padrão do export semanal.

## Technical Context

**Language/Version**: Python 3.12+ (executado via Poetry / Virtualenv)

**Primary Dependencies**: Prefect 3.6, SQLite3, SQLAlchemy / ResearchDomain (`CampusController`, `OrganizationController`, `ResearchGroupController`), Loguru

**Storage**: SQLite. Tabelas afetadas: `organizational_units` (repovoada com 23 campi reais, IDs realinhados aos já existentes em `research_groups.campus_id`), `organizations`, `teams.organization_id` (hoje NULL em 100% dos casos, recuperável do export histórico onde 342/344 grupos tinham `organization_id=1`).

**Testing**: Pytest (`tests/unit/`, `tests/test_backup_merger.py`, `tests/test_export_campus_resolver.py`)

**Target Platform**: Linux / GitHub Actions / Local CLI

**Project Type**: ETL Pipeline / Data Engineering

**Performance Goals**: Sem impacto perceptível — mudança de dados de referência (23 linhas) e lógica de export condicional, não de volume de processamento.

**Constraints**: Não reatribuir um grupo a um campus/organização que não é o seu (FR-004, FR-006); um grupo só é "resolvido" com campus **e** organização válidos (clarificação da spec); preservar a deduplicação por nome já existente para `organizational_units`, sem repetir o erro de forçar um ID fixo arbitrário (`id=1` para Serra) que colide com o esquema de IDs já usado em `research_groups.campus_id`.

**Scale/Scope**: 344 grupos de pesquisa, 23 campi reais, ~26 organizações (subconjunto relevante ao domínio de pesquisa).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [x] **Principle I (Ports & Adapters)**: Nenhuma mudança de porta — `research_group_exporter.py` já usa `CampusController`/`OrganizationController`/`ResearchGroupController` do `research-domain` via injeção; a correção é lógica interna de enriquecimento/filtragem, sem novo adapter.
- [x] **Principle II (Domain-First)**: Nenhum novo conceito de domínio introduzido; `Campus`/`Organization`/`ResearchGroup` já existem no `research-domain`. A correção restaura dados corretos para entidades já modeladas.
- [x] **Principle III (Prefect Flow)**: A validação institucional roda dentro da task já existente `export_groups_task` (`src/flows/exports/canonical_data.py`); nenhuma nova flow necessária. O repovoamento do catálogo ocorre em `backup_db_provisioner.py`, já orquestrado pela fase `merge_backup` do `weekly_orchestrator.py`.
- [x] **Principle IV (Audit-Driven Quality)**: O export semanal passa a reportar contagem de grupos excluídos/marcados por afiliação institucional não resolvida (FR-008/SC-004), tornando visível qualquer regressão futura no log de auditoria.
- [x] **Principle V (LGPD Compliance)**: Não aplicável — campus e organização não são dados pessoais; nenhuma mudança na camada de anonimização.

## Project Structure

### Documentation (this feature)

```text
specs/011-research-group-institutional-filtering/
├── plan.md              # Este plano de implementação
├── research.md          # Diagnóstico e decisões técnicas
├── data-model.md        # Modelagem do catálogo de campi/organizações e regras de resolução
└── quickstart.md        # Guia de verificação e testes manuais
```

*Sem diretório `contracts/`: nenhuma interface pública nova é criada; a mudança é interna ao `ResearchGroupExporter` e ao `BackupDatabaseProvisioner` já existentes.*

### Source Code (repository root)

```text
src/
├── core/
│   └── logic/
│       ├── backup_db_provisioner.py   # Repovoar organizational_units/organizations
│       │                               # a partir do export histórico recuperado
│       │                               # (23 campi, IDs realinhados), substituindo a
│       │                               # etapa "2. Organizational Units" atual
│       ├── backup_merger.py           # Remover a força de id=1 para "serra" na
│       │                               # limpeza de duplicatas (linhas 96-102); a
│       │                               # deduplicação por nome (linhas 146-152)
│       │                               # é preservada
│       └── research_group_exporter.py # Substituir fallback silencioso (linhas
│                                       # 90-107) por exclusão/flag explícita quando
│                                       # campus e/ou organização não resolvem
├── flows/
│   └── exports/
│       └── canonical_data.py          # export_groups_task: expor contagem de
│                                       # grupos excluídos/marcados no resumo do run
tests/
├── test_backup_merger.py              # Casos: catálogo de 23 campi provisionado
│                                       # corretamente, sem colisão de IDs
└── test_export_campus_resolver.py     # Casos: grupo com campus/organização válidos
                                        # é exportado normalmente; grupo com qualquer
                                        # um dos dois ausente é excluído/marcado
```

**Structure Decision**: Mudança concentrada em três módulos já existentes (`backup_db_provisioner.py`, `backup_merger.py`, `research_group_exporter.py`) mais uma exposição de contagem em `canonical_data.py`. Nenhum novo módulo, port ou flow — segue o mesmo padrão da feature 010, que já estabeleceu esses arquivos como o local correto para lógica de provisionamento/fusão/export de dados institucionais.

## Complexity Tracking

*Nenhuma violação da Constitution Check — seção não aplicável.*
