# Research: Research Group Institutional Filtering

## Diagnóstico Confirmado

**Estado atual (`db/horizon.db` e `data/backup/horizon_backup.db`)**:
- `organizational_units`: **1 linha** (`id=1, name='Serra'`).
- `research_groups.campus_id`: referencia **23 IDs distintos** (1–23), distribuição: `{1:29, 2:68, 3:17, 4:11, 5:18, 6:18, 7:10, 8:15, 9:24, 10:14, 11:12, 12:24, 13:8, 14:8, 15:15, 16:7, 17:8, 18:3, 19:6, 20:10, 21:14, 22:3, 23:2}` — total 344 grupos.
- `teams.organization_id`: **NULL para as 344 linhas**.
- `data/exports/novo_backup.zip` (arquivo canônico usado pelo provisionador atual) contém `campuses_canonical.json` com **apenas 1 campus** (`id=6, name='Serra'` no próprio arquivo de origem) — ou seja, o arquivo fonte usado hoje pelo provisionador **já não tem** o catálogo completo. Restaurar a partir dele não é suficiente.

## Decision: Fonte de recuperação do catálogo completo de campi

**Decision**: Usar o export canônico histórico anterior à regressão, recuperável do histórico do Git (`git show c12a3c8:data/exports/canonical_export_20260610_160943.zip`), como fonte de verdade para repovoar `organizational_units` e `organizations`.

**Rationale**: Esse arquivo (`canonical_export_20260610_160943.zip`, commit `c12a3c8`) contém:
- **23 campi reais e distintos** em `campuses_canonical.json`, com nomes e IDs completos: `1 Vila Velha, 2 Vitória, 3 Itapina, 4 Colatina, 5 Alegre, 6 Serra, 7 Guarapari, 8 Venda Nova do Imigrante, 9 Cachoeiro de Itapemirim, 10 São Mateus, 11 Piúma, 12 Cariacica, 13 Linhares, 14 Viana, 15 Santa Teresa, 16 Cefor, 17 Centro-Serrano, 18 Presidente Kennedy, 19 Ibatiba, 20 Nova Venécia, 21 Aracruz, 22 Montanha, 23 Barra de São Francisco`.
- **26 organizações** em `organizations_canonical.json`, incluindo `id=1 "Instituto Federal do Espirito Santo"`.
- `research_groups_canonical.json` do mesmo export mostra `organization_id=1` para **342 dos 344 grupos** — confirmando que a afiliação organizacional também é recuperável, não apenas a de campus.

**Achado crítico**: os `campus_id` já presentes hoje em `research_groups` (1–23) **correspondem exatamente ao esquema de IDs deste export histórico** (ex.: grupo id 1 tem `campus_id=1`, que neste export histórico é "Vila Velha" — não "Serra"). Isso prova que os dados de `research_groups.campus_id` nunca ficaram corrompidos; foi o catálogo de referência (`organizational_units`) que colapsou e, pior, **reatribuiu o ID 1 a "Serra"** (que historicamente era o campus de ID 6), causando uma colisão direta: os 29 grupos que pertencem ao campus_id=1 (originalmente "Vila Velha") hoje resolvem diretamente para `campus_map[1] = "Serra"` no exportador — não é apenas um fallback mascarando o problema, é uma correspondência de ID incorreta que rotula grupos errados com um nome de campus real, porém errado.

**Alternatives considered**:
- Reconstruir os nomes de campus a partir de `data/raw/sigpesq/` (dados brutos do scraper) foi considerado, mas o export histórico já oferece uma correspondência direta ID→nome sem necessidade de reprocessamento do scraper.
- Pedir a lista estática ao usuário/mantenedor foi descartado como primeira opção pois os dados já existem no repositório (histórico do Git), evitando dependência de fonte externa.

## Decision: Não reutilizar o ID 1 para "Serra"

**Decision**: Ao restaurar o catálogo, `organizational_units` deve usar os IDs **originais** do export histórico (Serra = 6, Vila Velha = 1, Vitória = 2, etc.), não o ID forçado (`id=1`) introduzido pela correção anterior de "Triple Campus Serra" (relatório seção 4.2).

**Rationale**: A correção anterior resolveu a duplicata visual (3 entradas "Serra") mas introduziu uma nova colisão ao fixar arbitrariamente `id=1` para Serra, sem verificar que esse ID já pertencia a outro campus real nos dados de `research_groups`. Usar os IDs originais do export histórico realinha `organizational_units` com os `campus_id` já armazenados em `research_groups`, sem exigir nenhuma migração de dados nos próprios grupos.

**Alternatives considered**: Manter `id=1` para Serra e remapear todos os 344 `research_groups.campus_id` para um novo esquema de IDs foi descartado — introduz uma migração de dados desnecessária e arriscada quando a alternativa (restaurar os IDs originais) não exige tocar em `research_groups` de forma alguma.

## Decision: Deduplicação deve continuar existindo, mas por nome+ID, não por "manter só o primeiro"

**Decision**: Preservar a lógica de deduplicação por nome (case-insensitive) já presente em `backup_merger.py:146-152` e `backup_db_provisioner.py:104-118`, mas sem forçar um ID fixo arbitrário — deduplicar significa "uma linha por nome real", não "colapsar tudo para o ID 1".

**Rationale**: O bug de "Triple Campus Serra" era real (múltiplas linhas para o mesmo campus com IDs diferentes) e a deduplicação por nome continua correta como conceito; o erro foi no *como* — ao invés de escolher determinar o ID por origem/precedência, o código simplesmente fixou `id=1`. A correção desta feature preserva a deduplicação, mas usando os IDs corretos do catálogo restaurado.

**Alternatives considered**: Remover a deduplicação completamente foi descartado — reintroduziria o bug original de campi duplicados.

## Decision: Validação institucional passa a ser obrigatória por padrão

**Decision**: `research_group_exporter.py` passa a excluir ou marcar explicitamente (`"unresolved_institutional_affiliation": true`) qualquer grupo cujo `campus_id` e/ou `organization_id` não resolvam para um registro real e conhecido, em vez de usar `next(iter(campus_map.values()))` / `next(iter(org_map.values()))` como fallback (linhas 91-107 atuais).

**Rationale**: Confirmado pela clarificação da spec — um grupo só é "resolvido" quando tem campus **e** organização válidos. O padrão atual de "garantir não-nulo para compatibilidade com o dashboard" é exatamente o mecanismo que mascara o problema.

**Alternatives considered**: Manter o fallback mas apenas logar um aviso foi descartado — não atende ao requisito FR-004/FR-006 de nunca reatribuir um grupo a um campus/organização que não é o seu.

## Decision: Escopo institucional no export semanal

**Decision**: `run_weekly()` (`src/flows/pipelines/weekly_orchestrator.py:122`) e a cadeia `export_canonical_task` → `export_groups_task` (`src/flows/exports/canonical_data.py`) continuam aceitando `campus_name: Optional[str] = None` para permitir exports filtrados por campus sob demanda, mas a validação de afiliação institucional (campus+organização resolvíveis) passa a ser aplicada **sempre**, independente do valor de `campus_name` — são preocupações ortogonais: uma filtra por campus específico, a outra garante que todo grupo exportado (de qualquer campus) tenha uma afiliação institucional real.

**Rationale**: Confirmado pelo relatório original — "the weekly export also runs with no institutional/campus scope... so nothing is filtered" refere-se à ausência de *validação*, não à ausência de um parâmetro de filtro por campus (que já existe e serve a outro propósito: exportar apenas 1 campus específico quando solicitado).

**Alternatives considered**: Exigir que `campus_name` seja sempre fornecido foi descartado — mudaria o comportamento padrão de "exportar todos os campi" para algo que a spec não pediu; o problema real é a falta de validação, não a falta de um filtro.
