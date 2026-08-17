# Feature Specification: Backup Database Merger (Fusão Resiliente de Dados Históricos)

**Feature Branch**: `010-backup-database-merger`

**Created**: 2026-08-15

**Status**: Draft

**Input**: User description: "Feature: Arquitetura de Banco de Backup e Fusão Resiliente (Backup Database Merger) no Horizon ETL"

## Clarifications

### Session 2026-08-15
- Q: O banco de backup de referência deve ser atualizado automaticamente ou permanecer somente-leitura? → A: Atualização automática do backup de referência apenas quando a execução semanal terminar com 100% de sucesso (sem falhas críticas).
- Q: Qual deve ser a precedência de atualização dos atributos da entidade durante a fusão? → A: Os dados novos da semana atualizam os campos do registro, preservando o ID único estável.
- Q: Como o sistema deve agir se o arquivo `horizon_backup.db` não existir? → A: Provisionar automaticamente o `horizon_backup.db` a partir do `novo_backup.zip` / `export.zip` na primeira inicialização.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Preservação e Fusão Automática de Dados quando Portais Externos Falham (Priority: P1)

Como mantenedor do ecossistema Horizon e usuário do Dashboard, quando o pipeline semanal do ETL for executado e uma ou mais fontes externas estiverem fora do ar ou fornecerem apenas dados parciais (por exemplo, o portal SigPesq inacessível ou o Lattes bloqueando requisições), o sistema deve automaticamente mesclar os dados históricos do banco de backup persistente (`data/backup/horizon_backup.db`) no banco ativo antes da exportação, garantindo que nenhum pesquisador, estudante, projeto ou artigo desapareça do export final.

**Why this priority**: É o valor central da feature e a causa raiz do problema atual: evitar perda catastrófica de dados em exports semanais.

**Independent Test**: Executar o pipeline semanal com conexão a serviços externos simulando falha total (ou offline); verificar se o `export.zip` final mantém a contagem integral de entidades históricas (10.089 pesquisadores, 4.691 iniciativas, 2.298 artigos, 173 orientações e 344 grupos).

**Acceptance Scenarios**:

1. **Given** um banco de backup de referência provisionado em `data/backup/horizon_backup.db` com 10.089 pesquisadores e 4.691 projetos, **When** o pipeline semanal roda em um banco de trabalho vazio e a fase do SigPesq/Lattes captura 0 novos dados, **Then** o merger complementa 100% dos dados faltantes do backup e o `export.zip` final contém todas as entidades históricas.
2. **Given** uma raspagem semanal que obteve com sucesso 5 novos projetos e 10 novos pesquisadores, **When** a fase de fusão roda, **Then** as novas entidades são inseridas/atualizadas sem duplicar os pesquisadores ou projetos já existentes no backup.

---

### User Story 2 - Provisionamento e Manutenção do Banco de Backup Persistente (Priority: P2)

Como administrador do ETL, quero ter um diretório persistente e protegido `data/backup/` contendo o banco de dados SQLite de referência (`horizon_backup.db`) gerado a partir do estado consolidado e validado (`novo_backup.zip`), de modo que resets de banco de dados ou execuções do pipeline semanal nunca apaguem ou corrompam esse backup.

**Why this priority**: Garante uma fonte de verdade imutável e estável para as operações de fusão e recuperação de desastres.

**Independent Test**: Disparar scripts de reset de banco e comandos do weekly pipeline; certificar que `data/backup/horizon_backup.db` permanece intacto e acessível com todos os seus registros originais.

**Acceptance Scenarios**:

1. **Given** a existência de `data/backup/horizon_backup.db`, **When** um comando de reset ou início de pipeline semanal é executado, **Then** o arquivo de backup de referência em `data/backup/` não é deletado nem modificado destrutivamente.
2. **Given** um ambiente recém-implantado sem o arquivo SQLite de backup mas com o archive `novo_backup.zip` / `export.zip`, **When** o sistema inicializa, **Then** o banco de referência em `data/backup/horizon_backup.db` é provisionado automaticamente a partir do arquivo canônico.

---

### User Story 3 - Compatibilidade e Integridade Total com o Dashboard (Priority: P3)

Como usuário final do Dashboard, quero que o arquivo `export.zip` gerado após a execução semanal seja carregado no Dashboard e gere o build estático sem erros, sem perfis nulos ou duplicados, e sem páginas em branco de pessoas ou grupos.

**Why this priority**: Garante que o consumidor final dos dados (o portal do Dashboard) funcione perfeitamente ponta a ponta.

**Independent Test**: Extrair o `export.zip` gerado no `horizon_dashboard` e executar `npm run build`; validar que todas as páginas de pesquisadores, estudantes, grupos, iniciativas e orientações são geradas com código de saída 0.

**Acceptance Scenarios**:

1. **Given** o `export.zip` gerado pelo pipeline com a fusão de backup, **When** o dashboard executa o build, **Then** 100% das páginas estáticas são construídas com sucesso sem erros de propriedades nulas (como `organization.name` ou `campus.name`).
2. **Given** a listagem de pesquisadores no dashboard, **When** qualquer pesquisador (incluindo pesquisadores históricos) é pesquisado, **Then** ele possui exatamente um único perfil associado a todos os seus projetos e artigos.

---

### Edge Cases

- O que acontece se o banco de backup estiver ausente ou corrompido? O sistema emite log de alerta e tenta provisioná-lo a partir do arquivo `novo_backup.zip` / `export.zip` mais recente.
- O que acontece se um registro da raspagem da semana tiver o mesmo identificador (Lattes ID / SigPesq ID) que um registro do backup mas com informações mais recentes? O merger atualiza os metadados mais recentes sem criar um novo registro com ID duplicado.
- O que acontece se a integridade referencial de um projeto exigir pesquisadores que não foram raspados na semana? O merger resolve as chaves estrangeiras garantindo que o pesquisador seja copiado do backup antes ou em conjunto com a iniciativa.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema DEVE manter uma pasta persistente `data/backup/` contendo o banco de dados de referência `horizon_backup.db` com o estado completo de entidades canônicas.
- **FR-002**: O sistema DEVE fornecer o módulo `BackupDatabaseMerger` capaz de comparar o banco SQLite ativo da semana com o banco de backup de referência.
- **FR-003**: O módulo de fusão DEVE mesclar registros ausentes de pesquisadores, estudantes, grupos de pesquisa, iniciativas, artigos, orientações e áreas de conhecimento para o banco ativo antes da exportação canônica.
- **FR-004**: O sistema DEVE garantir a unicidade de entidades utilizando identificadores canônicos estáveis (como `lattes_id`, `sigpesq_id` ou chave primária normalizada), impedindo duplicações de pessoas ou projetos.
- **FR-005**: O pipeline semanal (`weekly_orchestrator.py`) DEVE executar a etapa de fusão de backup imediatamente antes da exportação canônica (`export_canonical`).
- **FR-006**: O sistema DEVE preservar todas as pastas de relatórios de inteligência artificial (`project_sigpesq_files_json/`) e grafos de relacionamento durante e após as fases de exportação.
- **FR-007**: A exportação canônica DEVE garantir que todo grupo de pesquisa exportado possua os objetos `organization` e `campus` válidos e não-nulos.
- **FR-008**: O sistema DEVE sincronizar e atualizar o banco de referência `data/backup/horizon_backup.db` automaticamente ao final de uma execução semanal quando 100% das fases forem concluídas com sucesso.
- **FR-009**: Quando uma entidade existir simultaneamente no banco ativo e no backup, o merger DEVE aplicar as atualizações mais recentes coletadas na semana mantendo a chave primária canônica estável.
- **FR-010**: O sistema DEVE provisionar automaticamente o banco `data/backup/horizon_backup.db` a partir do archive canônico (`novo_backup.zip` / `export.zip`) caso o arquivo de banco não seja encontrado na inicialização.

### Key Entities

- **Backup Reference Database**: Banco SQLite fixo em `data/backup/horizon_backup.db` que armazena a totalidade histórica validada das entidades canônicas.
- **Active Working Database**: Banco SQLite utilizado pelas rotinas semanais para armazenar novos dados capturados na semana.
- **Canonical Entities**: Entidades acadêmicas estruturadas (Pesquisadores, Estudantes, Grupos, Iniciativas/Projetos, Artigos, Orientações).
- **Export Package**: Arquivo compactado canônico (`export.zip`) que abastece o Dashboard de visualização.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Execução do pipeline com fontes externas offline preserva 100% dos dados históricos (mínimo de 10.000 pesquisadores, 4.600 projetos, 2.200 artigos, 170 orientações e 340 grupos).
- **SC-002**: Zero duplicações de perfis gerados na base consolidada (cada pessoa possui exatamente um ID e um perfil).
- **SC-003**: O build do dashboard a partir do pacote exportado executa com 100% de sucesso (código de saída 0 e 0 páginas com falha de renderização).
- **SC-004**: A etapa de fusão de dados entre bancos SQLite executa em menos de 10 segundos durante o pipeline semanal.

## Assumptions

- O repositório `horizon_etl_h` possui acesso local ao arquivo `novo_backup.zip` / `export.zip` para provisionar o banco de referência inicial.
- As entidades possuem identificadores canônicos unívocos (como ID Lattes de 16 dígitos ou chave de origem do SigPesq) que viabilizam deduplicação determinística.
- O Dashboard consome os dados exclusivamente via arquivos exportados JSON / ZIP sem conexão direta ao banco SQLite.
