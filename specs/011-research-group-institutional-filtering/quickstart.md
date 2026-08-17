# Quickstart: Research Group Institutional Filtering

## Como Verificar e Testar a Funcionalidade

### 1. Confirmar o Estado Atual (antes da correção)

```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('db/horizon.db')
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM organizational_units')
print('organizational_units:', cur.fetchone()[0])
cur.execute('SELECT COUNT(*) FROM research_groups WHERE campus_id NOT IN (SELECT id FROM organizational_units)')
print('grupos com campus_id sem correspondência:', cur.fetchone()[0])
cur.execute('SELECT COUNT(*) FROM teams WHERE organization_id IS NULL')
print('teams com organization_id NULL:', cur.fetchone()[0])
"
```
Esperado hoje: `organizational_units: 1`, ~315 grupos sem correspondência, 344 teams com `organization_id` nulo.

### 2. Recuperar o Catálogo Histórico Completo (referência)

```bash
git show c12a3c8:data/exports/canonical_export_20260610_160943.zip > /tmp/old_export.zip
unzip -o /tmp/old_export.zip campuses_canonical.json organizations_canonical.json -d /tmp/old_export_peek
python3 -m json.tool /tmp/old_export_peek/campuses_canonical.json
```
Deve listar os 23 campi reais com seus IDs originais (Serra = id 6, não id 1).

### 3. Reprovisionar o Banco de Backup

```bash
python app.py init_backup_db
```
Após a correção, `organizational_units` deve conter 23 linhas com os IDs/nome do passo 2.

### 4. Rodar a Fusão

```bash
python app.py merge_backup
```

### 5. Verificar Novamente as Contagens

```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('db/horizon.db')
cur = conn.cursor()
cur.execute('SELECT id, name FROM organizational_units ORDER BY id')
print(cur.fetchall())
cur.execute('SELECT COUNT(*) FROM research_groups WHERE campus_id NOT IN (SELECT id FROM organizational_units)')
print('grupos ainda sem correspondência:', cur.fetchone()[0])
"
```
Esperado após a correção: 23 campi listados, 0 grupos sem correspondência de campus.

### 6. Validar a Exportação Canônica

```bash
python app.py export_canonical
python3 -c "
import json
data = json.load(open('data/exports/research_groups_canonical.json'))
from collections import Counter
print(Counter(g.get('campus', {}).get('name') for g in data))
print('grupos marcados/excluídos por afiliação não resolvida:', sum(1 for g in data if g.get('unresolved_institutional_affiliation')))
"
```
Esperado: distribuição real entre os 23 campi (não mais 100% "Serra"), com 0 fabricações.

### 7. Rodar Testes Automatizados

```bash
.venv/bin/pytest tests/test_backup_merger.py tests/test_export_campus_resolver.py
```

### 8. Verificar o Dashboard

```bash
cd horizon_dashboard && npm run build
```
Verificar que o dropdown de filtro por campus lista os campi reais com contagens plausíveis, sem "Serra" concentrando artificialmente todos os grupos.
