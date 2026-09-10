import json, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend import store
p=store.get(sys.argv[1]); truth=json.loads(Path('samples/tps7a20-ground-truth.json').read_text('utf-8'))
if p['demo'] or p['pdf_sha256']!=truth['sha256']: raise SystemExit('Wrong PDF or synthetic demo; benchmark refused.')
if not p['jobs'] or not any(j['stage']=='extract' and j['status']=='complete' for j in p['jobs']): raise SystemExit('No completed model extraction; accuracy is unavailable.')
actual={r['raw']['number']:r['raw']['original_name'] for r in p['pins'].values()}
expected=truth['pins']
report={'project_id':p['id'],'target':p['target'],'expected_package':truth['package'],'package_match_requires_human_review':True,'missing_numbers':sorted(set(expected)-set(actual)),'extra_numbers':sorted(set(actual)-set(expected)),'name_mismatches':{k:{'expected':expected[k],'actual':actual[k]} for k in expected.keys()&actual.keys() if expected[k]!=actual[k]},'evidence_page_mismatch':[n for n,r in p['pins'].items() if not any(e['page']==truth['pdf_page'] for e in r['raw']['evidence'])]}
out=Path('data')/f"benchmark-{p['id']}.json";out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(report)
