# Data Model: Knowledge Area Linkage Backfill

Nenhuma tabela nova é criada. Este documento descreve as entidades e relações existentes que passam a ser corretamente populadas, e as regras de integridade aplicadas durante o backfill.

## Entities

### KnowledgeArea (existente, sem mudança de schema)

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | INTEGER (PK) | Identificador canônico da área de conhecimento |
| `name` | VARCHAR | Nome da área (ex.: "Microrrede", "Metodologias Ágeis") |

- **Estado atual**: 1.530 linhas, totalmente populada. Nenhuma alteração de schema nesta feature (hierarquia explicitamente fora de escopo).

### ResearcherKnowledgeArea (junção, existente, hoje vazia)

| Campo | Tipo | Descrição |
|---|---|---|
| `researcher_id` | INTEGER (FK → researchers.id) | Pesquisador |
| `area_id` | INTEGER (FK → knowledge_areas.id) | Área de conhecimento associada |

- **Chave**: composta `(researcher_id, area_id)`, sem coluna `id` própria.
- **Regra de integridade (FR-008)**: se `area_id` referenciado no array aninhado de origem não existir em `knowledge_areas`, a associação é descartada com log/contagem de omissão — nunca inserida com FK quebrada.
- **Regra de não fabricação (FR-007)**: só é inserida uma linha quando o registro de origem (`researchers_canonical.json[].knowledge_areas[]`) contém explicitamente a associação.

### GroupKnowledgeArea (junção, existente, hoje vazia)

| Campo | Tipo | Descrição |
|---|---|---|
| `group_id` | INTEGER (FK → research_groups.id / teams.id) | Grupo de pesquisa |
| `area_id` | INTEGER (FK → knowledge_areas.id) | Área de conhecimento associada |

- Mesmas regras de integridade e não fabricação acima.
- Fonte: `research_groups_canonical.json[].knowledge_areas[]`.
- Já estava presente em `backup_merger.py: tables_to_merge`, mas nunca recebia dados do provisionador — corrigido nesta feature ao popular a origem.

### InitiativeKnowledgeArea (junção, existente, hoje vazia)

| Campo | Tipo | Descrição |
|---|---|---|
| `initiative_id` | INTEGER (FK → initiatives.id) | Iniciativa/projeto |
| `area_id` | INTEGER (FK → knowledge_areas.id) | Área de conhecimento associada |

- Mesmas regras de integridade e não fabricação acima.
- Fonte: `initiatives_canonical.json[].knowledge_areas[]`.
- **Ausente de `tables_to_merge`** — precisa ser adicionada ao merger, não só ao provisionador.

## Relationships

```text
Researcher  1 ──── * ResearcherKnowledgeArea * ──── 1  KnowledgeArea
ResearchGroup 1 ──── * GroupKnowledgeArea      * ──── 1  KnowledgeArea
Initiative  1 ──── * InitiativeKnowledgeArea   * ──── 1  KnowledgeArea
```

Todas as três são relações muitos-para-muitos clássicas via tabela de junção pura (sem atributos próprios além das duas FKs).

## Merge Rule (Provisioner → Backup DB → Active DB)

1. **Provisionamento** (`backup_db_provisioner.py`): para cada registro de pesquisador/grupo/iniciativa no arquivo canônico, iterar seu array aninhado `knowledge_areas` e `INSERT OR IGNORE` na tabela de junção correspondente do `data/backup/horizon_backup.db`.
2. **Fusão** (`backup_merger.py`, via `ATTACH DATABASE`): para as três tabelas de junção, copiar do backup para o ativo com `INSERT OR IGNORE` — união aditiva, nunca sobrescreve associações já presentes no banco ativo (decisão confirmada na clarificação da spec).
3. **Idempotência**: como as tabelas usam chave composta natural `(entidade_id, area_id)`, rodar o provisionamento ou a fusão múltiplas vezes não gera duplicatas nem efeitos colaterais.

## Validation Rules

- **FR-007** (não fabricar): uma associação só existe se estiver presente no array aninhado de origem — nenhuma inferência automática além do que já é feito hoje pelo `initiative_linker.py` para palavras-chave (User Story 3, tratado à parte).
- **FR-008** (não descartar silenciosamente): `area_id` sem correspondência em `knowledge_areas` é contado e reportado no resumo do provisionamento/fusão, não apenas ignorado sem rastro.
- **SC-005** (estabilidade entre execuções): a contagem de linhas nas três tabelas de junção não pode regredir para 0 após execuções subsequentes de `make weekly-flows`.
