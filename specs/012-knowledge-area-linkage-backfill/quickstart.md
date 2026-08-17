# Quickstart: Knowledge Area Linkage Backfill

## Como Verificar e Testar a Funcionalidade

### 1. Confirmar o Estado Atual (antes da correção)

```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('db/horizon.db')
cur = conn.cursor()
for t in ['researcher_knowledge_areas', 'group_knowledge_areas', 'initiative_knowledge_areas']:
    cur.execute(f'SELECT COUNT(*) FROM {t}')
    print(t, cur.fetchone()[0])
"
```
Esperado hoje: `0` para as três tabelas.

### 2. Reprovisionar o Banco de Backup

```bash
python app.py init_backup_db
```
Após a correção, o log deve indicar contagens de associações de área de conhecimento inseridas (não apenas contagens de entidades header).

### 3. Rodar a Fusão

```bash
python app.py merge_backup
```
O resumo de fusão (`summary: Dict[str, int]`) deve incluir chaves para `researcher_knowledge_areas`, `group_knowledge_areas` e `initiative_knowledge_areas` com contagens > 0.

### 4. Verificar Novamente as Contagens

```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('db/horizon.db')
cur = conn.cursor()
for t in ['researcher_knowledge_areas', 'group_knowledge_areas', 'initiative_knowledge_areas']:
    cur.execute(f'SELECT COUNT(*) FROM {t}')
    print(t, cur.fetchone()[0])
"
```
Esperado após a correção: contagens consistentes com os arrays aninhados presentes em `novo_backup.zip` (ex.: pesquisador id 14 deve ter pelo menos 2 associações — "Laboratório Multiusuário", "Microrrede").

### 5. Validar a Exportação Canônica

```bash
python app.py export_canonical
```
Verificar que `data/exports/knowledge_areas_mart.json` e o campo `knowledge_areas` em `initiatives_analytics_mart.json` deixam de retornar listas vazias.

### 6. Rodar Testes Automatizados

```bash
.venv/bin/pytest tests/test_backup_merger.py
```
Novos casos cobrem: provisionamento com áreas aninhadas presentes/ausentes, fusão aditiva quando ativo e backup divergem, e descarte seguro de `area_id` sem correspondência em `knowledge_areas`.

### 7. Validar Estabilidade Entre Execuções (SC-005)

```bash
python app.py weekly
python app.py weekly
```
As contagens das três tabelas de junção não devem regredir para 0 entre a primeira e a segunda execução.
