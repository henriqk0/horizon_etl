# Implementation Plan: Backup Database Merger (Fusão Resiliente de Dados Históricos)

**Branch**: `010-backup-database-merger` | **Date**: 2026-08-15 | **Spec**: [specs/010-backup-database-merger/spec.md](spec.md)

**Input**: Feature specification from `specs/010-backup-database-merger/spec.md`

## Summary

Implementar uma arquitetura de banco de backup persistente (`data/backup/horizon_backup.db`) e um módulo de fusão inteligente (`BackupDatabaseMerger`) que complementa automaticamente o banco SQLite da semana antes da exportação canônica. Isso impede a regressão e perda de dados históricos quando scrapers online (como SigPesq ou Lattes) falham ou são executados parcialmente.

## Technical Context

**Language/Version**: Python 3.12+ (executado via Poetry / Virtualenv)

**Primary Dependencies**: Prefect 3.6, SQLite3, SQLAlchemy / ResearchDomain, Loguru

**Storage**: SQLite (`data/backup/horizon_backup.db` como referência imutável; banco de trabalho ativo para ingestão semanal)

**Testing**: Pytest (`tests/unit/`, `tests/integration/`)

**Target Platform**: Linux / GitHub Actions / Local CLI

**Project Type**: ETL Pipeline / Data Engineering

**Performance Goals**: Etapa de fusão entre bancos SQLite via `ATTACH DATABASE` executada em < 5 segundos

**Constraints**: Preservação estrita da LGPD (PII anonimizada), zero duplicações de perfis/projetos, compatibilidade 100% com o build estático do Astro no `horizon_dashboard`

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [x] **Principle I (Ports & Adapters)**: `IBackupDatabaseMerger` port definido em `src/core/ports/backup_merger_port.py`. Lógica concreta em `src/core/logic/backup_merger.py`.
- [x] **Principle II (Domain-First)**: Entidades canônicas mapeadas diretamente no esquema do `research-domain`.
- [x] **Principle III (Prefect Flow)**: Etapa de fusão registrada como task/flow e orquestrada no `weekly_orchestrator.py`.
- [x] **Principle IV (Audit-Driven Quality)**: Emissão de relatório e contagem de entidades mescladas no log e rastreio de proveniência (`[BACKUP_DB]`).
- [x] **Principle V (LGPD Compliance)**: Dados anonimizados preservados conforme regras existentes.

## Project Structure

### Documentation (this feature)

```text
specs/010-backup-database-merger/
├── plan.md              # Este plano de implementação
├── research.md          # Decisões técnicas e arquitetura
├── data-model.md        # Modelagem de dados e regras de unicidade
├── quickstart.md        # Guia de execução e testes
├── contracts/
│   └── backup-merger.contract.md # Contrato da interface de fusão
└── checklists/
    └── requirements.md  # Checklist de qualidade da especificação
```

### Source Code

```text
src/
├── core/
│   ├── ports/
│   │   └── backup_merger_port.py      # Contrato de interface da fusão
│   └── logic/
│       ├── backup_merger.py           # Implementação da fusão SQLite ATTACH
│       ├── backup_db_provisioner.py   # Provisionador inicial de data/backup/
│       └── export_cache_bootstrapper.py
├── flows/
│   └── pipelines/
│       └── weekly_orchestrator.py     # Integração do step merge_backup
tests/
└── test_backup_merger.py              # Testes unitários cobrindo cenários de fusão
```

## Implementation Phases

### Phase 1: Provisionador de Backup (`backup_db_provisioner.py`)
1. Criar a pasta `data/backup/` se inexistente.
2. Ler o arquivo canônico consolidado (`novo_backup.zip` / `export.zip`) e popular o banco `data/backup/horizon_backup.db` com todas as 10.089 pessoas, 4.691 iniciativas, 2.298 artigos, 173 orientações e 344 grupos.
3. Proteger `data/backup/horizon_backup.db` contra comandos de reset destrutivo.

### Phase 2: Módulo de Fusão (`backup_merger.py`)
1. Criar a classe `BackupDatabaseMerger` implementando o port `IBackupDatabaseMerger`.
2. Executar conexão entre o banco da semana e o banco de backup via `ATTACH DATABASE`.
3. Para cada tabela (`campuses`, `organizations`, `researchers`, `students`, `research_groups`, `initiatives`, `articles`, `advisorships`):
   - Inserir registros que não foram encontrados no banco da semana.
   - Atualizar registros que receberam dados novos na semana, preservando IDs canônicos.
4. Integrar com o `ProvenanceTracker` para marcar itens recuperados como `[BACKUP_DB]`.

### Phase 3: Integração no Pipeline Semanal (`weekly_orchestrator.py`)
1. Adicionar o comando `merge_backup` na lista de fases (`_PHASES`) do `weekly_orchestrator.py`, posicionado antes de `consolidate_duplicates` e `export_canonical`.
2. Adicionar hook de sincronização do backup de referência quando 100% das fases forem concluídas com sucesso.

### Phase 4: Testes Automatizados e Validação
1. Criar suite de testes unitários em `tests/test_backup_merger.py`.
2. Validar cenário com raspagem vazia, raspagem parcial e raspagem completa.
3. Testar exportação final e validar o build no `horizon_dashboard`.
