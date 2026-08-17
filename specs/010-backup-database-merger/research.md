# Research: Backup Database Merger Architecture

## Technical Decisions

### 1. Mecanismo de Fusão entre Bancos SQLite (Attach vs Python Seeder)
- **Decisão**: Utilizar `sqlite3` `ATTACH DATABASE` associado ao ORM/SQL direto para mesclagem rápida entre o banco de trabalho ativo e o banco de backup de referência `data/backup/horizon_backup.db`.
- **Racional**: 
  - `ATTACH DATABASE` permite que o SQLite execute transferências e `INSERT OR IGNORE` / `INSERT OR REPLACE` diretamente no motor C do SQLite em microssegundos, sem o overhead de serializar milhares de registros em memória Python.
  - Para entidades que requerem resolução de relacionamentos (ex: projetos vinculados a pesquisadores), o merger utiliza queries com resolução por chaves canônicas (`lattes_id`, `sigpesq_id`, `name`).
- **Alternativas consideradas**:
  - *Leitura e re-inserção via JSON canônico*: Muito mais lento e sujeito a estouro de memória/AST.
  - *Substituição total de arquivo*: Inviabilizaria a captura de dados novos coletados durante a semana atual.

### 2. Localização e Formato do Banco de Referência
- **Decisão**: Salvar o banco de referência em `data/backup/horizon_backup.db`. Se ausente, o provisionamento inicial extrai os dados canônicos consolidados do arquivo `novo_backup.zip` / `export.zip` localizado em `data/exports/` ou raiz.
- **Racional**: Garante que o banco de backup seja auto-recuperável em novos deploys e ambientes CI/CD sem exigir dump binário committed no git.
- **Alternativas consideradas**:
  - Commitar o `.db` binário no Git (descartado para evitar inchaço de repositório).

### 3. Ponto de Inserção no Pipeline Semanal (`weekly_orchestrator.py`)
- **Decisão**: Inserir a fase `merge_backup` como um step pré-exportação, logo antes de `consolidate_duplicates` e `export_canonical`.
- **Racional**:
  - Permite que todas as fontes online (SigPesq, CNPq, Lattes) tentem rodar e capturar o que há de mais recente na semana.
  - Antes de gerar os JSONs canônicos de exportação, o `BackupDatabaseMerger` entra em ação e completa 100% dos dados que porventura não foram capturados pelas fontes online.
  - Em seguida, `consolidate_duplicates` e `export_canonical` operam sobre um banco SQLite 100% abastecido.

### 4. Atualização Automática do Banco de Backup
- **Decisão**: Ao final de uma execução semanal em que 100% das fases tenham concluído com sucesso (código de saída 0 e sem falhas críticas), o banco ativo é copiado/sincronizado para `data/backup/horizon_backup.db` com timestamp de versão.
- **Racional**: Garante que os novos dados e projetos descobertos passem a integrar o backup protegido para as próximas semanas.
