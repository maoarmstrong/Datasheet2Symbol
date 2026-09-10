"""Read-only real-document inspection plus upload; never pretends to call the model."""
from pathlib import Path
import sys, json, hashlib
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from backend.main import app
from backend.provider import render
path=Path('samples/tps7a20.pdf')
with TestClient(app) as client:
 p=client.post('/api/projects',files={'file':(path.name,path.read_bytes(),'application/pdf')}).json()
 assert p['page_count']==63 and not p['pins'] and not p['demo']
 assert client.get(f"/api/projects/{p['id']}/pdf").content==path.read_bytes()
 Path('samples/tps7a20-page4.jpg').write_bytes(render(path,4))
 print(json.dumps({'project_id':p['id'],'page_count':p['page_count'],'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'cloud_extraction':'NOT_RUN_NO_CREDENTIALS'}))
