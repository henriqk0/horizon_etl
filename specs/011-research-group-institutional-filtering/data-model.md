# Data Model: Research Group Institutional Filtering

Nenhuma tabela nova é criada. Este documento descreve as entidades de referência institucional existentes, os dados corretos a serem restaurados, e as regras de resolução aplicadas no export.

## Entities

### OrganizationalUnit / Campus (existente, catálogo a ser restaurado)

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | INTEGER (PK) | Identificador do campus — **deve usar os IDs originais do export histórico**, não um ID forçado |
| `name` | VARCHAR | Nome do campus real (ex.: "Vitória", "Cachoeiro de Itapemirim") |
| `organization_id` | INTEGER (FK → organizations.id) | Organização à qual o campus pertence |

- **Estado atual**: 1 linha (`id=1, name='Serra'`).
- **Estado alvo**: 23 linhas, recuperadas de `canonical_export_20260610_160943.zip` (commit `c12a3c8`):

  | id | name | id | name |
  |---|---|---|---|
  | 1 | Vila Velha | 13 | Linhares |
  | 2 | Vitória | 14 | Viana |
  | 3 | Itapina | 15 | Santa Teresa |
  | 4 | Colatina | 16 | Cefor |
  | 5 | Alegre | 17 | Centro-Serrano |
  | 6 | Serra | 18 | Presidente Kennedy |
  | 7 | Guarapari | 19 | Ibatiba |
  | 8 | Venda Nova do Imigrante | 20 | Nova Venécia |
  | 9 | Cachoeiro de Itapemirim | 21 | Aracruz |
  | 10 | São Mateus | 22 | Montanha |
  | 11 | Piúma | 23 | Barra de São Francisco |
  | 12 | Cariacica | | |

- **Regra crítica**: `id` deve ser preservado exatamente como no export histórico. Note que "Serra" é `id=6`, não `id=1` — o `id=1` pertence a "Vila Velha". A correção anterior ("Triple Campus Serra") havia forçado Serra para `id=1`, colidindo com os 29 grupos que já usavam `campus_id=1` para se referir a Vila Velha.
- **Deduplicação**: uma linha por `lower(name)` único — preserva a intenção da correção anterior sem repetir o erro de ID fixo.

### Organization (existente, catálogo a ser restaurado)

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | INTEGER (PK) | Identificador da organização |
| `name` | VARCHAR | Nome da organização (ex.: "Instituto Federal do Espirito Santo") |

- **Estado atual**: `teams.organization_id` é NULL para os 344 grupos (não se sabe se `organizations` em si está vazia ou apenas desvinculada — a verificação faz parte da implementação).
- **Estado alvo**: `organization_id=1` ("Instituto Federal do Espirito Santo") restaurado para os grupos que o tinham no export histórico (342 dos 344 grupos).

### ResearchGroup (existente, sem mudança de schema)

| Campo | Tipo | Descrição |
|---|---|---|
| `campus_id` | INTEGER (FK → organizational_units.id) | **Já correto e presente** — não requer migração, apenas realinhamento do catálogo referenciado |
| `organization_id` | INTEGER (FK → organizations.id) | **Ausente (NULL)** — requer backfill a partir do export histórico |

## Relationships

```text
ResearchGroup * ──── 1  OrganizationalUnit (Campus)
ResearchGroup * ──── 1  Organization
OrganizationalUnit * ──── 1  Organization
```

## Resolution Rule (Export-Time Validation)

Um grupo é considerado **institucionalmente resolvido** (exportável normalmente) somente quando:
1. `campus_id` corresponde a uma linha real em `organizational_units` (catálogo restaurado de 23 campi), **E**
2. `organization_id` corresponde a uma linha real em `organizations`.

Se qualquer uma das duas condições falhar:
- O grupo é excluído do export canônico, **ou**
- É marcado explicitamente com `"unresolved_institutional_affiliation": true` (a decisão entre excluir vs. marcar é um detalhe de implementação a ser definido em `/speckit-tasks`; a spec permite ambos — FR-005).
- Em nenhum caso o grupo recebe um campus ou organização que não é o seu (proibido: `next(iter(campus_map.values()))` como fallback).

## Validation Rules

- **FR-004/FR-006** (não reatribuir): remover completamente os fallbacks `elif campus_map: ... next(iter(...))` e `else: {"id": 1, "name": "Serra"}` / `{"id": 1, "name": "Instituto Federal do Espírito Santo"}` de `research_group_exporter.py`.
- **FR-008** (visibilidade): cada execução de export reporta a contagem de grupos excluídos/marcados por afiliação institucional não resolvida.
- **SC-001**: proporção de grupos com campus não resolvido cai de 91,6% para 0% (para os grupos cujo campus histórico é recuperável — todos os 344, dado que o catálogo completo foi localizado).
- **SC-003**: catálogo de campi restaurado não contém duplicatas por nome.
