# Fluxos e Entrypoints

## Entry points principais

Os pontos de entrada mais relevantes hoje sao:

- `make full-refresh` — executa pipeline completo + export canonico + ZIP
- `make pipeline CAMPUS=Serra` — executa pipeline para um campus + ZIP
- `make weekly-flows` — executa pipelines semanais + ZIP
- `make export-canonical CAMPUS=Serra` — exporta dados canonicos + ZIP
- `make ingest-sigpesq`
- `make ingest-lattes-full`
- `python app.py full_pipeline Serra data/exports`
- `python app.py export_canonical data/exports`
- `python app.py weekly data/exports`
- `python app.py all_sources Serra`
- `python app.py sigpesq`
- `python app.py cnpq_sync Serra`

## Organizacao dos flows

Os flows agora ficam separados por origem ou responsabilidade:

- `src/flows/sigpesq/`: grupos, projetos, planos de trabalho e flow SigPesq completo.
- `src/flows/lattes/`: download, projetos, orientacoes e flow Lattes completo.
- `src/flows/cnpq/`: sincronizacao de grupos CNPq.
- `src/flows/exports/`: exportacao canonica, marts e grafo de pessoas.
- `src/flows/pipelines/`: pipelines operacionais que combinam ingestao e exportacao.
- `src/flows/all.py`: flow geral de ingestao que chama todas as fontes.

Nao ha wrappers de compatibilidade no topo de `src/flows`; use sempre os caminhos
por pasta, como `src.flows.sigpesq.all` ou `src.flows.exports.canonical_data`.

## Comando recomendado para refresh completo

O comando mais importante para operacao e:

```bash
make full-refresh
```

Ele executa:

1. limpeza do banco local
2. recriacao do schema
3. subida do Prefect Server local
4. execucao do pipeline unificado para todos os campi

## Fluxo unificado

O `full_ingestion_pipeline` coordena, em alto nivel:

1. ingestao SigPesq
2. ingestao Lattes
3. sincronizacao CNPq
4. exportacoes canonicas
5. geracao de marts
6. escrita de reports operacionais

> **Consolidacao de duplicatas removida dos pipelines automaticos.**  
> O `PersonConsolidator` anteriormente era executado automaticamente apos a
> ingestao de cada pipeline (`unified.py`, `weekly.py`), mas usava correspondencia
> exclusiva por nome para deletar registros de pesquisadores, causando perda de
> dados. A consolidacao manual continua disponivel como script avulso:
> ```bash
> python src/scripts/consolidate_duplicates.py
> ```

Ao final de cada pipeline, o `app.py` chama automaticamente o script
`scripts/export_zip.py` para compactar todos os JSONs gerados em um unico ZIP
`export.zip`, sobrescrevendo um ZIP anterior de mesmo nome.

O processo de geracao inclui:

1. **Limpeza** — grafos relacionais de grupos da execucao anterior sao removidos;
   symlinks sao eliminados antes da compactacao.
2. **Compactacao** — todos os JSONs sao zipados com `ZIP_DEFLATED`.
3. **Validacao** — o ZIP e verificado contra a lista de arquivos esperados e
   a consistencia dos manifests de grafos. Se falhar, o ZIP e deletado.
4. **Limpeza pos-zip** — JSONs soltos e diretorios vazios sao removidos.

### Protecao LGPD nas exportacoes

Durante a exportacao, todos os dados passam por anonimizacao antes de serem
serializados:

- CPF (`identification_id`) → `LGPD-<sha256>`
- E-mails → `<hash>@anon.lgpd` (inclusive em campos de texto livre)
- Telefones em payloads fonte → anulados

Alem do hook de banco de dados (ORM session hook), os metodos de exportacao
(`export_researchers`, `export_initiatives`, `export_advisorships`) aplicam
`scrub_pii_deep` em cada registro como camada defensiva adicional.

## Lattes

O download de curriculos Lattes chama `scriptLattes`. Essa dependencia ainda
usa Selenium internamente, entao o flow valida a compatibilidade entre o
Chrome/Chromium local e o `./chromedriver` antes de limpar `data/lattes_json` e
baixar novos JSONs.

Quando existir mais de um navegador instalado, informe o binario desejado:

```bash
CHROME_BINARY=/caminho/para/chrome make ingest-lattes-download
CHROME_BINARY=/caminho/para/chrome make ingest-lattes-full
```

Antes da chamada final ao `scriptLattes`, o flow baixa em paralelo os curriculos
ausentes no cache bruto `cache/`. O padrao usa 3 workers para reduzir o tempo de
download sem abrir muitas sessoes do Chrome de uma vez. Ajuste com
`HORIZON_LATTES_DOWNLOAD_WORKERS`; desative com `HORIZON_LATTES_PREFETCH=0`.

## Fluxos legados

Alguns alvos ainda existem para casos especificos:

- `pipeline-serra`
- `sync-cnpq`
- `export`

Esses atalhos sao uteis para execucao parcial, mas nao substituem o `full-refresh` quando a intencao e reconstruir o estado completo.
