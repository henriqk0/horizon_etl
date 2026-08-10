# Data Model & Schema Specification: SigPesq Project Report Extraction

**Feature Branch**: `006-sigpesq-pdf-mistral-extraction`  
**Date**: 2026-08-10  

## Data Entities

### 1. Extracted Project Report JSON (`data/exports/project_sigpesq_files_json/PJ_<CODE>.json`)

The JSON artifact produced by the Mistral AI extraction pipeline conforms to the following schema:

```json
{
  "codigo": "6020",
  "titulo": "Desenvolvimento de Plataforma de IA",
  "descricao": "Descrição detalhada das atividades de pesquisa...",
  "palavras_chave": ["IA", "Aprendizado de Máquina", "ETL"],
  "area_conhecimento": "Ciência da Computação",
  "linha_pesquisa": "Inteligência Artificial e Processamento de Linguagem Natural",
  "objetivos": {
    "geral": "Desenvolver modelos avançados de IA para análise de dados acadêmicos.",
    "especificos": [
      "Extrair dados estruturados de relatórios em PDF.",
      "Integrar a base de dados com o repositório de iniciativas."
    ]
  },
  "coordenador": {
    "nome": "Maria Silva",
    "cpf": "***.123.456-**",
    "titulacao": "Doutorado"
  },
  "equipe": [
    {
      "nome": "João Santos",
      "funcao": "Pesquisador",
      "ch_semanal": 20
    }
  ],
  "datas": {
    "inicio": "2024-01-01 00:00:00.000000",
    "fim": "2025-12-31 00:00:00.000000"
  },
  "cronograma": [
    {
      "atividade": "Levantamento bibliográfico",
      "inicio": "2024-01-01",
      "fim": "2024-03-31"
    }
  ],
  "financiamento": {
    "orgao_fomento": "CNPq",
    "valor": 50000.0
  },
  "_meta": {
    "arquivo": "PJ 6020.pdf",
    "paginas": 12,
    "extraido_em": "2026-08-10T14:30:00.000000+00:00",
    "modelo": "mistral-large-latest",
    "fonte_texto": "pdf-text",
    "campos_ausentes": []
  }
}
```

### 2. Validation & Alignment Rules

- **LGPD Compliance (Principle V)**: PII fields (CPF) in coordinator and team members MUST be masked/anonymized before saving output JSON files.
- **Enrichment Integration**: The `_meta` block maps directly to `EnrichmentPayload` fields in `src/core/logic/project_enrichment.py`.
- **Primary Identifier**: Filename stem or `codigo` field (e.g. `PJ 6020` or `6020`).
