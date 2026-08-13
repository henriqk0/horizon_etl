# Dados e Artefatos

## Pastas principais

### `data/raw/`

Armazena os arquivos brutos baixados das fontes, principalmente SigPesq e Lattes.

### `data/exports/`

Contem um arquivo ZIP unico por execucao com todos os JSONs canonicos, grafos e
marts gerados pelo pipeline. O ZIP e produzido automaticamente ao final de cada
pipeline (`make full-refresh`, `make weekly-flows`, `make pipeline`,
`make export-canonical`) com o nome `export.zip`. Se um `export.zip` ja existe
em `data/exports`, ele e sobrescrito.

Antes da compactacao, o script `scripts/export_zip.py`:
1. Remove grafos relacionais de grupos da execucao anterior.
2. Remove symlinks.
3. Compacta os JSONs com `ZIP_DEFLATED`.
4. Valida o ZIP contra a lista de arquivos esperados e a consistencia dos
   manifests de grafos (ZIP invalido e deletado).
5. Remove os JSONs soltos e diretorios vazios.

Os dados exportados passam por anonimizacao de CPF, e-mails e telefones
(protecao LGPD) antes da serializacao.

A estrutura completa do ZIP esta documentada no
[README](../README.md#estrutura-do-zip-de-export-canonico).

### `data/reports/`

Contem os relatorios operacionais e de auditoria. Exemplos:

- `etl_flow_run.md`
- `etl_load_report.md`
- `tracking_audit_report.md`
- `weekly_pipeline_run.json`
- `weekly_pipeline_run.md`

O report semanal inclui uma secao de warnings por fonte. Ela destaca achados
estruturados como duplicidades restantes, tracking com status inesperado e
problemas conhecidos de extracao, por exemplo nomes sentinela vindos do CNPq.

### `db/horizon.db`

Banco SQLite local usado durante a execucao e a validacao do pipeline.

## Artefatos publicados na automacao semanal

A workflow semanal foi preparada para publicar:

- a pasta `data`
- o banco `db/horizon.db`

Isso facilita auditoria, download dos resultados e analise posterior da execucao.

Esses arquivos sao saidas de runtime. A politica operacional e consumir os
artefatos pelo GitHub Actions e evitar commits automaticos de resultados gerados.
Snapshots em `data/exports/` ou `data/reports/` so devem ser versionados quando
houver curadoria explicita para documentacao, auditoria ou reproducao de casos.
