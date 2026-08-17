# Research: Knowledge Area Linkage Backfill

## Diagnóstico Confirmado

**Contagens observadas (idênticas em `db/horizon.db` e `data/backup/horizon_backup.db`)**:

| Tabela | Linhas |
|---|---|
| `knowledge_areas` | 1.530 |
| `research_groups` | 344 |
| `researchers` | 10.089 |
| `initiatives` | 4.692 |
| `group_knowledge_areas` | **0** |
| `researcher_knowledge_areas` | **0** |
| `initiative_knowledge_areas` | **0** |

**Schema das tabelas de junção** (verificado via `PRAGMA table_info`):
- `group_knowledge_areas(group_id INTEGER, area_id INTEGER)` — chave composta
- `researcher_knowledge_areas(researcher_id INTEGER, area_id INTEGER)` — chave composta
- `initiative_knowledge_areas(initiative_id INTEGER, area_id INTEGER)` — chave composta
- `knowledge_areas(id INTEGER PK, name VARCHAR)`

**Evidência de que os dados de origem existem** — `data/exports/novo_backup.zip` contém arrays aninhados `"knowledge_areas": [{"id": ..., "name": ...}, ...]` diretamente em cada registro de:
- `researchers_canonical.json` (ex.: pesquisador id 14, "Pablo Rodrigues Muniz" → áreas "Laboratório Multiusuário", "Microrrede")
- `research_groups_canonical.json` (ex.: grupo id 1 → áreas "Aulas de campo...", "Divulgação científica...")
- `initiatives_canonical.json` (ex.: iniciativa id 1 → áreas "Processo", "Metodologias Ágeis")

## Decision: Causa raiz é dupla, não única

**Decision**: Tratar como dois defeitos sequenciais e corrigir ambos, não apenas um.

**Rationale**:
1. **Provisionador não lê os arrays aninhados.** Em `src/core/logic/backup_db_provisioner.py:241-248`, a etapa "10. Knowledge Areas" só executa `INSERT OR REPLACE INTO knowledge_areas (id, name)` a partir de `knowledge_areas_canonical.json` — a lista "header" das áreas. A etapa seguinte, "11. JUNCTION TABLES" (linha 250+), reconstrói `article_authors`, `team_members`, `initiative_persons` e `advisorship_members` lendo campos aninhados (`r.get("articles", [])`, `init.get("team", [])`, `adv.get("advisorships", [])`) dos mesmos registros — mas não existe um bloco equivalente lendo `r.get("knowledge_areas", [])`, `group.get("knowledge_areas", [])` ou `init.get("knowledge_areas", [])`. É uma omissão, não um bug de lógica: o padrão já está estabelecido no arquivo, só falta replicá-lo.
2. **Mesmo corrigido o provisionador, a fusão (merge) ainda descartaria 2 das 3 tabelas.** Em `src/core/logic/backup_merger.py:72-90`, `tables_to_merge` inclui `"group_knowledge_areas"` mas omite `"researcher_knowledge_areas"` e `"initiative_knowledge_areas"`. Um banco de backup corretamente provisionado ainda assim não propagaria essas duas tabelas para o banco ativo.

**Alternatives considered**: Corrigir apenas o merger (assumindo que o provisionador já popula as tabelas) foi descartado porque a contagem 0 em **ambos** os bancos (ativo e backup) prova que o problema começa no provisionamento, não apenas na fusão.

## Decision: Padrão de implementação — replicar o padrão de junção existente

**Decision**: A nova sub-etapa "11e. Knowledge Area Associations" no provisionador usará `INSERT OR IGNORE INTO {tabela} ({entidade}_id, area_id) VALUES (?, ?)` para cada entrada aninhada `knowledge_areas` em pesquisadores, grupos e iniciativas — mesmo padrão de idempotência já usado em `article_authors` (linha 257) e `initiative_persons` (linha 284).

**Rationale**: Consistência com o código existente reduz risco de regressão e facilita revisão; `INSERT OR IGNORE` com chave composta natural (sem coluna `id` própria) já garante deduplicação sem necessidade de lógica adicional.

**Alternatives considered**: Criar uma tabela de staging intermediária foi descartado por complexidade desnecessária — o volume (~1-3 vínculos por registro × ~15k registros) é trivial para SQLite síncrono.

## Decision: Resolução de conflitos no merge — união aditiva

**Decision**: Ao adicionar `researcher_knowledge_areas` e `initiative_knowledge_areas` a `tables_to_merge`, usar a mesma estratégia `INSERT OR IGNORE` já aplicada às demais tabelas de junção do merger — associações da fonte ativa e do backup são unidas, nenhuma é sobrescrita.

**Rationale**: Confirmado com o usuário (clarificação da spec) — consistente com o comportamento não destrutivo já estabelecido para `article_authors`/`team_members`/`advisorship_members` no mesmo merger.

**Alternatives considered**: Precedência de uma fonte sobre a outra foi rejeitada por introduzir uma exceção ao padrão aditivo já em produção, sem benefício claro.

## Decision: Hierarquia de áreas de conhecimento — fora de escopo

**Decision**: Não adicionar coluna `parent_id`/`code` a `knowledge_areas` nesta feature.

**Rationale**: Confirmado com o usuário. O modelo atual (`research_domain/domain/entities/knowledge_area.py`) só tem `id` e `name`; introduzir hierarquia é uma mudança de schema maior e independente do bug crítico (0 vínculos), que deve ser tratada como uma spec futura separada.

## Gaps secundários no pipeline de ingestão ao vivo (User Story 3, P3)

**Decision**: Corrigir dois pontos já identificados na investigação, escopados como menor prioridade (P3) por afetarem apenas atualizações incrementais, não o volume total:

1. `src/core/logic/research_group_loader.py:187-227` — `knowledge_area_ids` só é setado no branch de criação de grupo (`if not group_already_existed`); o branch `group_already_existed` (linha 280+) nunca re-sincroniza áreas de conhecimento quando os dados de origem mudam.
2. `src/core/logic/initiative_linker.py:313-328` — `associate_keyword_knowledge_areas` retorna cedo (`if not keywords_str: return`) quando `metadata.keywords` está ausente, mesmo que outras evidências (áreas do grupo/pesquisadores vinculados) pudessem sugerir uma área razoável.

**Rationale**: Estes gaps são independentes da causa raiz principal (tabelas de junção zeradas) e não bloqueiam as User Stories 1 e 2, mas são necessários para que o Sucesso SC-005 ("dados permanecem estáveis ou crescem após rodadas semanais consecutivas") se sustente ao longo do tempo para grupos/iniciativas atualizados incrementalmente.

**Alternatives considered**: Deixar para uma spec futura foi considerado, mas como já estão documentados como FR-009/FR-010 na spec aprovada, mantidos no escopo desta feature (User Story 3, prioridade P3 — pode ser implementada de forma independente das demais).
