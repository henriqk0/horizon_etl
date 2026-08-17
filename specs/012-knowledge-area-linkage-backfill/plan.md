# Implementation Plan: Knowledge Area Linkage Backfill

**Branch**: `012-knowledge-area-linkage-backfill` | **Date**: 2026-08-15 | **Spec**: [specs/012-knowledge-area-linkage-backfill/spec.md](spec.md)

**Input**: Feature specification from `specs/012-knowledge-area-linkage-backfill/spec.md`

## Summary

Corrigir a fusão de dados de backup (`BackupDatabaseMerger` / `BackupDatabaseProvisioner`) para que as tabelas de junção `researcher_knowledge_areas`, `group_knowledge_areas` e `initiative_knowledge_areas` sejam efetivamente populadas — hoje as três estão em 0 linhas em ambos os bancos (ativo e backup), apesar de `knowledge_areas` (1.530), `research_groups` (344), `researchers` (10.089) e `initiatives` (4.692) estarem completos. Os dados de vínculo já existem no arquivo canônico (`novo_backup.zip`), aninhados em `researchers_canonical.json`, `research_groups_canonical.json` e `initiatives_canonical.json`, mas nunca são lidos pelo provisionador. Adicionalmente, corrige o pipeline de ingestão ao vivo para ressincronizar vínculos de grupos existentes e para não depender exclusivamente de `metadata.keywords` ao vincular iniciativas.

## Technical Context

**Language/Version**: Python 3.12+ (executado via Poetry / Virtualenv)

**Primary Dependencies**: Prefect 3.6, SQLite3, SQLAlchemy / ResearchDomain, Loguru

**Storage**: SQLite (`data/backup/horizon_backup.db` como referência imutável; `db/horizon.db` como banco de trabalho ativo). Tabelas afetadas: `researcher_knowledge_areas(researcher_id, area_id)`, `group_knowledge_areas(group_id, area_id)`, `initiative_knowledge_areas(initiative_id, area_id)`, `knowledge_areas(id, name)`.

**Testing**: Pytest (`tests/unit/`, `tests/test_backup_merger.py`)

**Target Platform**: Linux / GitHub Actions / Local CLI

**Project Type**: ETL Pipeline / Data Engineering

**Performance Goals**: Backfill de todas as associações de área de conhecimento durante o provisionamento/fusão existente, sem aumento perceptível no tempo total de `merge_backup` (atualmente < 5s via `ATTACH DATABASE`).

**Constraints**: Não fabricar vínculos sem evidência na fonte (FR-007); não sobrescrever vínculos existentes — apenas unir aditivamente (FR-005, `INSERT OR IGNORE`, mesmo padrão de `article_authors`/`team_members`); hierarquia de áreas de conhecimento fica fora de escopo.

**Scale/Scope**: ~1.530 áreas de conhecimento; até ~3 vínculos aninhados por registro em ~10.089 pesquisadores, 344 grupos e 4.692 iniciativas conforme observado no arquivo fonte.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [x] **Principle I (Ports & Adapters)**: Nenhuma mudança de assinatura em `IBackupDatabaseMerger` (`src/core/ports/backup_merger_port.py`) — `merge()` já retorna um dicionário de contagens por tabela; as novas tabelas apenas passam a ser incluídas nesse retorno. A lógica concreta permanece em `src/core/logic/backup_merger.py` e `src/core/logic/backup_db_provisioner.py`.
- [x] **Principle II (Domain-First)**: Vínculos de área de conhecimento já são um relacionamento existente no `research-domain` (`researcher.knowledge_areas`, `group.knowledge_areas`, `initiative.knowledge_areas`); esta correção apenas restaura a persistência desses relacionamentos, sem introduzir novos conceitos de domínio.
- [x] **Principle III (Prefect Flow)**: A correção ocorre dentro das etapas já registradas (`merge_backup` em `weekly_orchestrator.py`); nenhuma nova flow é necessária.
- [x] **Principle IV (Audit-Driven Quality)**: O resumo de fusão (`summary: Dict[str, int]`) passará a reportar contagens reais para as três tabelas de junção de áreas de conhecimento, tornando visível qualquer regressão futura (SC-005 do spec).
- [x] **Principle V (LGPD Compliance)**: Não aplicável — áreas de conhecimento não são dados pessoais.

## Project Structure

### Documentation (this feature)

```text
specs/012-knowledge-area-linkage-backfill/
├── plan.md              # Este plano de implementação
├── research.md          # Decisões técnicas e diagnóstico consolidado
├── data-model.md        # Modelagem das tabelas de junção e regras de merge
└── quickstart.md        # Guia de verificação e testes manuais
```

*Sem diretório `contracts/`: o contrato `IBackupDatabaseMerger` já existe (feature 010) e não muda de assinatura — apenas o conteúdo do dicionário de retorno de `merge()` ganha novas chaves.*

### Source Code (repository root)

```text
src/
├── core/
│   └── logic/
│       ├── backup_db_provisioner.py   # Adicionar leitura dos arrays aninhados
│       │                               # "knowledge_areas" em researchers/
│       │                               # research_groups/initiatives e inserção
│       │                               # nas 3 tabelas de junção (nova sub-etapa 11e)
│       ├── backup_merger.py           # Adicionar "researcher_knowledge_areas" e
│       │                               # "initiative_knowledge_areas" a tables_to_merge
│       ├── research_group_loader.py   # Ressincronizar knowledge_area_ids também
│       │                               # para grupos já existentes (não só na criação)
│       └── initiative_linker.py       # associate_keyword_knowledge_areas: derivar
│                                       # áreas também sem metadata.keywords
├── flows/
│   └── pipelines/
│       └── weekly_orchestrator.py     # Sem mudança estrutural; contagens do merge_backup
│                                       # já expostas no log passam a refletir as novas tabelas
tests/
└── test_backup_merger.py              # Novos casos: provisionamento e fusão de
                                        # researcher/group/initiative_knowledge_areas
```

**Structure Decision**: Mudança cirúrgica dentro dos módulos já estabelecidos pela feature 010 (`backup_db_provisioner.py`, `backup_merger.py`), seguindo o mesmo padrão usado para as tabelas de junção `article_authors`/`team_members`/`advisorship_members`. Nenhum novo módulo, port ou flow é criado; os ajustes em `research_group_loader.py` e `initiative_linker.py` (User Story 3, P3) tocam apenas os pontos já identificados na investigação como responsáveis pelos gaps do pipeline ao vivo.

## Complexity Tracking

*Nenhuma violação da Constitution Check — seção não aplicável.*
