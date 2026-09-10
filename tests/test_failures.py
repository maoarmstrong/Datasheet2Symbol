import json
from pathlib import Path
import pytest
from backend import provider, store
from backend.main import worker, new_project

def compact_payload(pins):
 evidence=[];table_rows=[];compact=[]
 for pin in pins:
  evidence_ids=[]
  for item in pin['evidence']:
   if item not in evidence: evidence.append(item)
   evidence_ids.append(evidence.index(item))
  table_row_id=None
  if pin.get('table_row'):
   if pin['table_row'] not in table_rows: table_rows.append(pin['table_row'])
   table_row_id=table_rows.index(pin['table_row'])
  compact.append({key:pin[key] for key in ['number','original_name','electrical_type','part','position','kind','fact','observation','issues']} | {'evidence_ids':evidence_ids,'table_row_id':table_row_id})
 return {'evidence':evidence,'table_rows':table_rows,'pins':compact,'notes':[]}

def full_payload(pins):
 return {'pins':pins,'notes':[]}

@pytest.mark.parametrize('mode',['truncated','malformed','foreign_page'])
def test_model_output_rejected(monkeypatch,mode):
 monkeypatch.setenv('DASHSCOPE_API_KEY','mock-key');monkeypatch.setenv('DASHSCOPE_BASE_URL','https://example.invalid/v1')
 class FakeClient:
  def __init__(self,**kwargs): pass
  def __enter__(self): return self
  def __exit__(self,*args): pass
  def post(self,*args,**kwargs):
   class Response:
    status_code=200
    def json(self):
     return {'choices':[{'finish_reason':'length' if mode=='truncated' else 'stop','message':{'content':'invalid json' if mode=='malformed' else json.dumps({'candidates':[],'relevant_pages':[99] if mode=='foreign_page' else [],'notes':[]})}}]}
   return Response()
 monkeypatch.setattr(provider.httpx,'Client',FakeClient)
 with pytest.raises(ValueError): provider.invoke(Path('fixtures/power.pdf'),[1],'scan',None)

def test_rate_limit_retries_bounded(monkeypatch):
 monkeypatch.setenv('DASHSCOPE_API_KEY','mock-key');monkeypatch.setenv('DASHSCOPE_BASE_URL','https://example.invalid/v1')
 calls=[]
 class FakeClient:
  def __init__(self,**kwargs): pass
  def __enter__(self): return self
  def __exit__(self,*args): pass
  def post(self,*args,**kwargs):
   calls.append(1)
   return type('Response',(),{'status_code':429})()
 monkeypatch.setattr(provider.httpx,'Client',FakeClient);monkeypatch.setattr(provider.time,'sleep',lambda _:None)
 with pytest.raises(ValueError,match='429'): provider.invoke(Path('fixtures/power.pdf'),[1],'scan',None)
 assert len(calls)==3

def test_failed_batch_resume_does_not_repeat_success(monkeypatch):
 p=new_project('test',Path('fixtures/power.pdf').read_bytes())
 p['jobs']=[{'id':'test-job','stage':'scan','target':None,'status':'running','batches':[{'pages':[1],'status':'pending','error':''},{'pages':[2],'status':'pending','error':''}]}]
 store.save(p);calls=[]
 def invoke(path,pages,stage,target):
  calls.append(pages)
  if pages==[2] and calls.count([2])==1: raise ValueError('temporary failure')
  return {'candidates':[],'relevant_pages':pages,'notes':[]},{'model':'MOCK'}
 monkeypatch.setattr(provider,'invoke',invoke)
 worker(p['id'],'test-job');p=store.get(p['id'])
 assert p['jobs'][0]['status']=='failed'
 worker(p['id'],'test-job');p=store.get(p['id'])
 assert p['jobs'][0]['status']=='complete' and calls==[[1],[2],[2]]

def test_relaxed_validation_accepts_mismatch_with_warning(monkeypatch):
 """With relaxed table_row validation, a number mismatch is accepted with a warning instead of rejected."""
 monkeypatch.setenv('DASHSCOPE_API_KEY','mock-key');monkeypatch.setenv('DASHSCOPE_BASE_URL','https://example.invalid/v1')
 fixture=json.loads(Path('fixtures/power.json').read_text('utf-8'));payload=full_payload([fixture['pins'][0]])
 class FakeClient:
  def __init__(self,**kwargs): pass
  def __enter__(self): return self
  def __exit__(self,*args): pass
  def post(self,*args,**kwargs):
   value={**payload['pins'][0],'number':'999'}
   response_payload={'pins':[value],'notes':[]}
   class Response:
    status_code=200
    def json(self): return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(response_payload)}}],'usage':{'total_tokens':100}}
   return Response()
 monkeypatch.setattr(provider.httpx,'Client',FakeClient)
 result,audit=provider.invoke(Path('fixtures/power.pdf'),[1],'extract',fixture['target'])
 # Relaxed: accepts the pin but adds warning to observation
 assert result['pins'][0]['number']=='999'
 assert 'warning' in result['pins'][0].get('observation','').lower()
