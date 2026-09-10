import base64, copy, hashlib, json, os, sys, threading, time, uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
import fitz
from fastapi import FastAPI, File, Form, UploadFile, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from . import store, provider, exporter, orcad_ascii
from .models import RunRequest, EditRequest, TargetRequest, PartsRequest, AIConfigRequest, VisionConfigRequest, ModelConfigRequest, Pin, Candidate

# Concurrent batches speed up multi-page scans. Bailian's RPM limit is high (30k/min),
# so 2-3 parallel vision calls are safe; keep it modest to stay well under rate limits.
pool = ThreadPoolExecutor(max_workers=3)
def now(): return datetime.now(timezone.utc).isoformat()

@asynccontextmanager
async def lifespan(app):
    with store.LOCK:
        for p in store.all_projects():
            for j in p['jobs']:
                if j['status']=='running':
                    j['status']='failed'
                    for b in j['batches']:
                        if b['status']!='complete': b.update(status='failed', error='服务已重启，请重试未完成批次')
            store.normalize_symbol_names(p)
            store.normalize_positions(p)
            store.normalize_electrical_types(p)
            store.save(p)
    yield

app = FastAPI(title='Datasheet2Symbol', lifespan=lifespan)

@app.middleware('http')
async def local_only(request: Request, call_next):
    # Prevent DNS rebinding: only accept requests addressed to loopback hosts.
    # A malicious domain resolving to 127.0.0.1 would carry its own Host header.
    host = (request.headers.get('host') or '').split(':')[0]
    if host and host not in ('127.0.0.1', 'localhost', '::1', 'testserver'):
        return Response('Invalid host', 403)
    # Cross-origin protection: reject any request carrying a foreign Origin, including
    # reads (GET). Direct navigation and same-origin fetches carry no or a matching Origin.
    origin = request.headers.get('origin')
    if origin and origin != str(request.base_url).rstrip('/'):
        return Response('Cross-origin request rejected', 403)
    return await call_next(request)

def new_project(name, pdf, demo=False):
    pid=uuid.uuid4().hex
    try:
        with fitz.open(stream=pdf,filetype='pdf') as doc:
            if doc.needs_pass or not 0 < len(doc) <= 2000: raise ValueError()
            count=len(doc)
    except Exception: raise HTTPException(400,'PDF 无效、加密或页数超过 2000')
    p={'schema_version':1,'id':pid,'name':name,'demo':demo,'page_count':count,'pdf_sha256':hashlib.sha256(pdf).hexdigest(),'revision':0,'target':None,'candidates':[],'relevant_pages':[],'pins':{},'parts':['1'],'jobs':[],'history':[],'undo':[],'created':now()}
    store.save(p); store.pdf_path(pid).write_bytes(pdf)
    return p

@app.post('/api/shutdown')
def shutdown():
    """Stop the server and exit the process (used by the in-app quit button)."""
    def _do():
        time.sleep(0.4)
        os._exit(0)
    threading.Thread(target=_do, daemon=True).start()
    return {'status': 'shutting down'}

@app.get('/api/config')
def configuration():
    c=provider.config()
    a=provider.ascii_config()
    return {'model':c['model'],'provider':c.get('provider','DashScope'),'configured':c['configured'],'vision':c.get('vision',True),'ascii':{'provider':a['provider'],'model':a['model'],'configured':a['configured']},'export':'通用审核 Excel；支持 AMD/Xilinx ASCII Pinout → OrCAD 粘贴表'}

@app.post('/api/ai/config')
def configure_ai(body: AIConfigRequest):
    try:
        provider.configure_runtime(body.provider, body.base_url, body.model, body.api_key)
        return provider.test_connection()
    except ValueError as exc:
        raise HTTPException(400, str(exc))

@app.post('/api/vision/config')
def configure_vision(body: VisionConfigRequest):
    try:
        provider.configure_vision(body.base_url, body.model, body.api_key)
        return provider.test_vision_connection()
    except ValueError as exc:
        raise HTTPException(400, str(exc))

@app.get('/api/models')
def models(): return provider.list_models()

@app.post('/api/models')
def add_model(body: ModelConfigRequest):
    try:
        return provider.upsert_model(body.name, body.base_url, body.model, body.api_key)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

@app.delete('/api/models/{name}')
def remove_model(name: str): return provider.delete_model(name)

@app.post('/api/models/select')
def choose_model(body: dict):
    try:
        return provider.select_model(body.get('name', ''))
    except ValueError as exc:
        raise HTTPException(400, str(exc))

@app.post('/api/models/fetch')
def fetch_models(body: dict):
    try:
        return {'models': provider.fetch_model_list(body.get('base_url', ''), body.get('api_key', ''))}
    except ValueError as exc:
        raise HTTPException(400, str(exc))

@app.post('/api/benchmark')
def benchmark(body: dict):
    import time
    pid = body.get('project_id')
    stage = body.get('stage', 'extract')
    model_names = body.get('models') or []
    if not pid or not model_names:
        raise HTTPException(400, '请提供项目 ID 和模型列表')
    p = store.get(pid)
    pages = body.get('pages') or []
    if not pages:
        pages = p['relevant_pages'] if stage == 'extract' else list(range(1, p['page_count'] + 1))
    if not pages or any(n < 1 or n > p['page_count'] for n in pages):
        raise HTTPException(400, '页码越界')
    if stage == 'extract' and not p['target']:
        raise HTTPException(400, '提取对比需先确认目标封装')

    def run_one(name):
        m = provider.find_model(name)
        if not m:
            return {'model': name, 'error': '模型不存在'}
        cfg = {'provider': 'DashScope', 'base_url': m['base_url'], 'model': m['model'], 'api_key': m['api_key'], 'configured': True, 'vision': True}
        t0 = time.time()
        try:
            result, audit = provider.invoke(store.pdf_path(pid), pages, stage, p['target'], cfg_override=cfg)
            count = len(result.get('pins', [])) if stage == 'extract' else len(result.get('candidates', []))
            pins = {pin['number']: pin['original_name'] for pin in result.get('pins', [])} if stage == 'extract' else None
            return {'model': name, 'model_id': m['model'], 'duration': round(time.time() - t0, 2), 'count': count, 'tokens': audit.get('usage', {}).get('total_tokens'), 'pins': pins, 'error': None}
        except Exception as e:
            return {'model': name, 'model_id': m['model'], 'duration': round(time.time() - t0, 2), 'count': None, 'error': str(e)[:300]}

    with ThreadPoolExecutor(max_workers=len(model_names)) as ex:
        results = list(ex.map(run_one, model_names))
    results.sort(key=lambda r: (r['duration'] is None, r['duration'] or 0))
    return {'results': results}

@app.post('/api/orcad/ascii/convert')
async def convert_ascii_pinout(file: UploadFile=File(...), max_pins_per_section: int=Form(100), use_ai: bool=Form(False)):
    raw=await file.read(8*1024*1024+1)
    if len(raw)>8*1024*1024:
        raise HTTPException(413,'ASCII Pinout 文件最大 8 MB')
    try:
        suggester=provider.suggest_ascii_roles if use_ai else None
        device, data, _, _=orcad_ascii.convert_ascii_pinout(raw,max_pins_per_section,suggester)
    except ValueError as exc:
        raise HTTPException(400,str(exc))
    filename=''.join(c for c in device if c not in '\\/:*?"<>|').strip() or 'XILINX_FPGA'
    return Response(data,media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':f'attachment; filename="{filename}_OrCAD_Pinlist.xlsx"'})

def project_status(p):
    """Derive a coarse workflow status for the sidebar overview."""
    running=[j for j in p['jobs'] if j['status']=='running']
    if any(j['stage']=='extract' for j in running): return 'extracting'
    if running: return 'scanning'
    if not p['jobs']: return 'new'
    if not p['target']: return 'pending_target'
    if not any(j['stage']=='extract' and j['status']=='complete' for j in p['jobs']): return 'pending_extract'
    if any(r['review']!='confirmed' for r in p['pins'].values()): return 'pending_review'
    return 'done'

@app.get('/api/projects')
def projects(): return [{'id':p['id'],'name':p['name'],'demo':p['demo'],'status':project_status(p)} for p in store.all_projects()]

@app.post('/api/projects')
async def upload(file: UploadFile=File(...)):
    data=await file.read(80*1024*1024+1)
    if len(data)>80*1024*1024: raise HTTPException(413,'PDF 最大 80 MB')
    return new_project(file.filename or 'datasheet.pdf',data)

@app.get('/api/projects/{pid}')
def project(pid:str): return store.get(pid)

@app.get('/api/projects/{pid}/pdf')
def pdf(pid:str): return FileResponse(store.pdf_path(pid),media_type='application/pdf')

@app.get('/api/projects/{pid}/pages/{page}')
def page_image(pid:str,page:int):
    p=store.get(pid)
    if not 1<=page<=p['page_count']: raise HTTPException(400,'页码越界')
    return Response(provider.render(store.pdf_path(pid),page),media_type='image/jpeg')

def ensure_idle(p):
    if any(j['status']=='running' for j in p['jobs']): raise HTTPException(409,'解析任务运行中，请等待完成')

def checkpoint(p,action):
    p['undo'].append({k:copy.deepcopy(p[k]) for k in ['pins','parts','target']})
    p['undo']=p['undo'][-30:]
    p['history'].append({'time':now(),'action':action,'revision':p['revision']})
    p['revision']+=1

@app.post('/api/projects/{pid}/target')
def target(pid:str, body:TargetRequest):
    with store.LOCK:
        p=store.get(pid); store.check_revision(p,body.revision); ensure_idle(p)
        if p['pins'] and p['target'] != body.candidate.model_dump(): raise HTTPException(409,'已有引脚时不能切换目标；请重新上传创建独立项目以免混合封装')
        if any(e.page>p['page_count'] for e in body.candidate.evidence): raise HTTPException(400,'来源页越界')
        checkpoint(p,'确认目标'); p['target']=body.candidate.model_dump(); store.save(p); return p

def _process_batch(pid,jid,index,batch):
    job=next(j for j in store.get(pid)['jobs'] if j['id']==jid)
    if batch['status']=='complete': return
    t0 = time.time()
    try:
        result,audit=provider.invoke(store.pdf_path(pid),batch['pages'],job['stage'],job['target'])
        with store.LOCK:
            p=store.get(pid); j=next(j for j in p['jobs'] if j['id']==jid)
            if j['stage']=='scan':
                for c in result['candidates']:
                    existing=next((x for x in p['candidates'] if (x['model'],x['package'],x['pin_count'])==(c['model'],c['package'],c['pin_count'])),None)
                    if existing: existing['evidence']+= [e for e in c['evidence'] if e not in existing['evidence']]
                    else: p['candidates'].append(c)
                p['relevant_pages']=sorted(set(p['relevant_pages']+result['relevant_pages']))
                p['revision']+=1
            else:
                store.merge(p,result['pins'])
                for pin in result['pins']:
                    if pin['part'] not in p['parts']: p['parts'].append(pin['part'])
            j['batches'][index].update(status='complete',error='',audit=audit,result=result,duration=round(time.time()-t0,2))
            store.save(p)
    except Exception as e:
        with store.LOCK:
            p=store.get(pid); j=next(j for j in p['jobs'] if j['id']==jid)
            # Never include network request headers or secret-bearing exception text.
            msg=str(e) if isinstance(e,ValueError) and 'validation' not in str(e).lower() else '响应格式/结构校验失败或页面处理失败，请缩小批次重试'
            j['batches'][index].update(status='failed',error=msg[:500],audit=getattr(e,'audit',{}),duration=round(time.time()-t0,2)); store.save(p)

def worker(pid,jid):
    job=next(j for j in store.get(pid)['jobs'] if j['id']==jid)
    pending=[(i,b) for i,b in enumerate(job['batches']) if b['status']!='complete']
    # Run incomplete batches concurrently (model calls are the slow part; the SQLite writes
    # are serialized by store.LOCK). This turns an N-batch scan from N×T into roughly N/3×T.
    with ThreadPoolExecutor(max_workers=3) as ex:
        list(ex.map(lambda item: _process_batch(pid,jid,item[0],item[1]), pending))
    with store.LOCK:
        p=store.get(pid); j=next(j for j in p['jobs'] if j['id']==jid)
        j['status']='complete' if all(b['status']=='complete' for b in j['batches']) else 'failed'
        store.save(p)

@app.post('/api/projects/{pid}/runs')
def run(pid:str,body:RunRequest):
    with store.LOCK:
        p=store.get(pid); ensure_idle(p)
        if p['demo']: raise HTTPException(400,'演示项目禁止伪装为云端解析；请上传真实 PDF')
        if not provider.config()['configured']: raise HTTPException(400,'请先在后端环境变量配置百炼 API Key 与 API 地址，然后重启服务')
        if body.stage=='extract' and not p['target']: raise HTTPException(400,'必须先确认型号和封装')
        # Extract defaults to relevant_pages; user can override with explicit page list.
        # For large pin counts, suggest narrower range to avoid truncation.
        default_extract_pages = p['relevant_pages'] if body.stage=='extract' else list(range(1,p['page_count']+1))
        pages=sorted(set(body.pages or default_extract_pages))
        if not pages or any(n<1 or n>p['page_count'] for n in pages): raise HTTPException(400,'请选择有效 PDF 文件页码')
        # For extraction, use single-page batches when pin count is high or pages are dense,
        # to reduce truncation risk. Scan stays at 2 pages for efficiency.
        batch_size = 1 if body.stage == 'extract' and (p['target'] or {}).get('pin_count',0) >= 20 else 2
        j={'id':uuid.uuid4().hex,'stage':body.stage,'target':p['target'],'status':'running','created':now(),'batches':[{'pages':pages[i:i+batch_size],'status':'pending','error':''} for i in range(0,len(pages),batch_size)]}
        p['jobs'].append(j); store.save(p); pool.submit(worker,pid,j['id']); return p

@app.post('/api/projects/{pid}/runs/{jid}/retry')
def retry(pid:str,jid:str):
    with store.LOCK:
        p=store.get(pid); ensure_idle(p)
        j=next((j for j in p['jobs'] if j['id']==jid),None)
        if not j or j['status']!='failed': raise HTTPException(400,'没有可重试的失败批次')
        j['status']='running'; store.save(p); pool.submit(worker,pid,jid); return p

@app.patch('/api/projects/{pid}/pins')
def edit(pid:str,body:EditRequest):
    with store.LOCK:
        p=store.get(pid); store.check_revision(p,body.revision)
        if not body.numbers or any(n not in p['pins'] for n in body.numbers): raise HTTPException(400,'请选择有效引脚')
        allowed={'number','symbol_name','electrical_type','part','position','kind','observation','review'}
        if set(body.values)-allowed: raise HTTPException(400,'不允许修改此字段')
        review=body.values.get('review','unreviewed')
        if review not in ['unreviewed','confirmed']: raise HTTPException(400,'审核状态无效')
        values={k:v for k,v in body.values.items() if k!='review'}
        if 'number' in values and (len(body.numbers)!=1 or any(store.effective(r)['number']==values['number'] for key,r in p['pins'].items() if key not in body.numbers)):
            raise HTTPException(400,'物理脚号必须唯一，且只能逐个修改')
        for n in body.numbers:
            try: pin=Pin.model_validate({**store.effective(p['pins'][n]),**values})
            except Exception: raise HTTPException(400,'引脚字段无效')
            if pin.part not in p['parts']: raise HTTPException(400,'请先创建 Part')
        checkpoint(p,{'edit':body.numbers,'values':body.values})
        for n in body.numbers:
            r=p['pins'][n]; r['edits'].update(values); r['review']=review
        store.normalize_symbol_names(p)
        store.save(p); return p

@app.post('/api/projects/{pid}/pins')
def add_pin(pid:str,body:dict):
    with store.LOCK:
        p=store.get(pid); store.check_revision(p,body.get('revision')); ensure_idle(p)
        number=body.get('number')
        if not isinstance(number,str) or not number.strip() or any(store.effective(r)['number']==number for r in p['pins'].values()): raise HTTPException(400,'新脚号必须为非空且唯一的字符串')
        page=body.get('page')
        if not isinstance(page,int) or not 1<=page<=p['page_count']: raise HTTPException(400,'来源页越界')
        pin=Pin(number=number,original_name='',symbol_name='',fact='uncertain',part=p['parts'][0],issues=['人工补录，请核对名称、结构类型与电气属性'],evidence=[{'page':page,'kind':'table','quote':'人工补录，待核对'}]).model_dump()
        checkpoint(p,{'add_pin':number})
        p['pins']['manual-'+uuid.uuid4().hex]={'raw':pin,'edits':{},'review':'unreviewed','conflicts':[],'versions':[pin]}
        store.save(p); return p

@app.put('/api/projects/{pid}/parts')
def parts(pid:str,body:PartsRequest):
    with store.LOCK:
        p=store.get(pid); store.check_revision(p,body.revision)
        if len(set(body.parts))!=len(body.parts) or any(not x.strip() for x in body.parts): raise HTTPException(400,'Part 名称不能重复或为空')
        if any(store.effective(r)['part'] not in body.parts for r in p['pins'].values()): raise HTTPException(400,'请先移动该 Part 的引脚')
        checkpoint(p,'调整 Parts'); p['parts']=body.parts; store.save(p); return p

@app.post('/api/projects/{pid}/undo')
def undo(pid:str,body:dict):
    with store.LOCK:
        p=store.get(pid); store.check_revision(p,body.get('revision')); ensure_idle(p)
        if not p['undo']: raise HTTPException(400,'没有可撤销的编辑')
        p.update(p['undo'].pop()); p['revision']+=1; p['history'].append({'time':now(),'action':'撤销'}); store.save(p); return p

@app.get('/api/projects/{pid}/validation')
def validation(pid:str): return {'errors':exporter.validate(store.get(pid))}

@app.get('/api/projects/{pid}/export/{kind}')
def download(pid:str,kind:str):
    p=store.get(pid)
    if kind=='json':
        p['pdf_base64']=base64.b64encode(store.pdf_path(pid).read_bytes()).decode()
        data=json.dumps(p,ensure_ascii=False).encode(); mime='application/json'
    elif kind in ['xlsx','tsv']:
        # Generic review exports intentionally allow unresolved values and keep review metadata.
        try: data=exporter.export(p,kind)
        except ValueError as e: raise HTTPException(400,str(e))
        mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' if kind=='xlsx' else 'text/tab-separated-values'
    else: raise HTTPException(404)
    # Filename uses the confirmed chip model when available, falling back to the PDF name.
    base=(p['target'] or {}).get('model') or Path(p['name']).stem or 'datasheet'
    base=''.join(c for c in base if c not in '\\/:*?"<>|').strip() or 'datasheet'
    return Response(data,media_type=mime,headers={'Content-Disposition':f'attachment; filename="{base}.{kind}"'})

@app.post('/api/import')
async def import_project(file:UploadFile=File(...)):
    data=await file.read(120*1024*1024+1)
    if len(data)>120*1024*1024: raise HTTPException(413,'JSON 过大')
    try:
        p=json.loads(data); pdf=base64.b64decode(p.pop('pdf_base64'),validate=True)
        if p['schema_version']!=1 or hashlib.sha256(pdf).hexdigest()!=p['pdf_sha256']: raise ValueError()
        if p['target']: Candidate.model_validate(p['target'])
        for n,r in p['pins'].items():
            Pin.model_validate(r['raw']); Pin.model_validate(store.effective(r))
            if r['review'] not in ['confirmed','unreviewed','conflict']: raise ValueError()
        fresh=new_project(p['name'],pdf,bool(p['demo']))
        p['id']=fresh['id']; p['page_count']=fresh['page_count']; p['undo']=[]
        for j in p['jobs']:
            if j['status']=='running': j['status']='failed'
        for r in p['pins'].values():
            if any(e['page']>p['page_count'] for e in r['raw']['evidence']): raise ValueError()
        store.normalize_symbol_names(p)
        store.normalize_positions(p)
        store.save(p); return p
    except Exception: raise HTTPException(400,'项目 JSON 无效或 PDF 校验失败')

@app.post('/api/demo/{sample}')
def demo(sample:str):
    path=Path(__file__).parent.parent/'fixtures'/f'{sample}.json'
    if sample not in ['power','digital','connector','multipage']: raise HTTPException(404)
    fixture=json.loads(path.read_text('utf-8'))
    pdf=(Path(__file__).parent.parent/'fixtures'/f'{sample}.pdf').read_bytes()
    p=new_project('DEMO · '+fixture['name'],pdf,True)
    p['target']=fixture['target']; p['candidates']=[fixture['target']]
    store.merge(p,fixture['pins']); p['parts']=list(dict.fromkeys(x['part'] for x in fixture['pins']))
    p['jobs']=[{'id':'mock','stage':'extract','status':'complete','batches':[{'pages':[1,2],'status':'complete','error':'','audit':{'model':'MOCK — NOT CLOUD','prompt_version':'fixture-v1','usage':{}}}]}]
    store.save(p); return p

def _app_root():
    # When frozen by PyInstaller, assets unpack to sys._MEIPASS; otherwise the repo root.
    return Path(getattr(sys, '_MEIPASS', Path(__file__).parent.parent))

dist=_app_root()/'frontend'/'dist'
if dist.exists(): app.mount('/',StaticFiles(directory=dist,html=True),name='frontend')
