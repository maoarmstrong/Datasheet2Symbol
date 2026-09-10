from pathlib import Path
import io,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from backend.main import app
from backend import store
pid='06769a71954d4dfbaeeca7de0193bfe5'
p=store.get(pid);truth=json.loads(Path('samples/tps7a20-ground-truth.json').read_text('utf-8'))
assert {store.effective(r)['number']:store.effective(r)['symbol_name'] for r in p['pins'].values()}==truth['pins']
assert all(r['review']=='confirmed' for r in p['pins'].values())
out=Path('output');out.mkdir(exist_ok=True)
client=TestClient(app)
for kind in ['xlsx','tsv','json']:
 response=client.get(f'/api/projects/{pid}/export/{kind}');assert response.status_code==200
 (out/f'TPS7A20-DBV-reviewed.{kind}').write_bytes(response.content)
wb=load_workbook(out/'TPS7A20-DBV-reviewed.xlsx');rows=list(wb['Pins'].values)
assert len(rows)==6 and all(r[3:5]==('Visible','Line') and r[10]=='confirmed' for r in rows[1:])
assert {r[0]:r[1] for r in rows[1:]}==truth['pins']
assert {r[0]:r[7] for r in rows[1:]}=={'1':'B','2':'B','3':'A','4':'A','5':'B'}
assert rows[4][2]=='Unknown'
snapshot=json.loads((out/'TPS7A20-DBV-reviewed.json').read_text('utf-8'));assert snapshot['pins']==p['pins']
print('Real reviewed sample: 5 rows, correct names, unique Part assignment, Visible/Line, Unknown NC retained. XLSX/TSV/JSON saved.')
