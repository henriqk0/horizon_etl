# Quickstart: Backup Database Merger

## Como Utilizar e Testar a Funcionalidade

### 1. Provisionar o Banco de Backup de Referência
O banco de backup em `data/backup/horizon_backup.db` é provisionado automaticamente ao rodar o pipeline, ou manualmente via:
```bash
python app.py init_backup_db
```

### 2. Executar a Fusão de Backup no Pipeline Semanal
A fusão roda automaticamente durante a execução semanal:
```bash
python app.py weekly
```

Para disparar apenas a fase de fusão de dados entre os bancos:
```bash
python app.py merge_backup
```

### 3. Verificar o Relatório de Fusão
Ao final da etapa de fusão, o log indicará a quantidade de registros complementados:
```text
[INFO] BackupDatabaseMerger: Sincronizados 4347 iniciativas, 3513 pesquisadores, 2247 artigos a partir do banco de backup.
```

### 4. Rodar Testes Automatizados
```bash
.venv/bin/pytest tests/test_backup_merger.py
```
