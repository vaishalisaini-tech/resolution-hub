import os,json,uuid,time,sys,tempfile,subprocess,base64,re,io
from pathlib import Path
from fastapi import HTTPException
from bs4 import BeautifulSoup
from .db import db,settings
from .security import require,check_secrets
from .content import clean,text

def scan(path,required):
    if not required:return
    try:r=subprocess.run([os.getenv('CLAMSCAN_PATH','clamscan'),'--no-summary',str(path)],capture_output=True,timeout=45)
    except Exception:raise HTTPException(503,'Attachment scanner unavailable; upload rejected')
    if r.returncode!=0:raise HTTPException(422,'Attachment scan failed or detected unsafe content; upload rejected')

def can_read(c,user,asset):
    permission=next((p for p in ['solve','knowledge.read','knowledge.create','knowledge.edit'] if p in user['permissions']),None)
    if not permission:raise HTTPException(403,'Attachment access denied')
    require(user,permission,asset['workspace'])
    if asset['owner']==user['id']:return
    if 'knowledge.read' in user['permissions'] and c.execute('SELECT 1 FROM knowledge_assets WHERE asset_id=?',(asset['id'],)).fetchone():return
    raise HTTPException(403,'Attachment is private')
def get_asset(c,aid,user,workspace=None,own=False):
    a=c.execute('SELECT * FROM assets WHERE id=?',(aid,)).fetchone()
    if not a:raise HTTPException(404,'Attachment not found')
    if workspace and a['workspace']!=workspace:raise HTTPException(403,'Cross-workspace attachment denied')
    if own and a['owner']!=user['id']:raise HTTPException(403,'Only your own uploads may be attached')
    can_read(c,user,a);return dict(a)
def expand(c,ids):
    found=set(ids);pending=list(ids)
    while pending:
        for r in c.execute('SELECT child FROM asset_children WHERE parent=?',(pending.pop(),)):
            if r[0] not in found:found.add(r[0]);pending.append(r[0])
        if len(found)>100:raise HTTPException(422,'Too many nested attachments')
    return found

def upload(data,name,workspace,user):
    if 'knowledge.create' not in user['permissions'] and 'solve' not in user['permissions']:raise HTTPException(403,'Upload not permitted')
    require(user,'solve' if 'solve' in user['permissions'] else 'knowledge.create',workspace)
    ext=Path(name).suffix.lower()
    if ext not in ['.txt','.md','.log','.csv','.json','.eml','.msg','.pdf','.docx','.png','.jpg','.jpeg','.webp']:raise HTTPException(415,'Unsupported file format')
    with db() as c:cfg=settings(c)
    if len(data)>cfg['upload_mb']*1024*1024:raise HTTPException(413,'Upload too large')
    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/('input'+ext);p.write_bytes(data);out=Path(td)/'result.json'
        required=cfg['require_scan'] or os.getenv('UPLOAD_SCAN')=='required' or os.getenv('APP_ENV')=='production'
        scan(p,required)
        try:
            result=subprocess.run([sys.executable,'-m','app.extract_worker',str(p),name,str(out)],capture_output=True,timeout=40)
            parsed=json.loads(out.read_text())
        except Exception:raise HTTPException(422,'Extraction failed or exceeded its resource/time limit')
        if result.returncode or 'error' in parsed:raise HTTPException(422,parsed.get('error','Extraction failed'))
        # Scan every decoded nested payload too, not just the outer mail/archive.
        def scan_children(node):
            for i,ch in enumerate(node.get('children',[])):
                child_path=Path(td)/str(uuid.uuid4());child_path.write_bytes(base64.b64decode(ch['data']));scan(child_path,required);scan_children(ch['result'])
        scan_children(parsed)
    budget=[0,0]
    with db() as c:
        def save(payload,filename,node):
            budget[0]+=1;budget[1]+=len(payload)
            if budget[0]>80 or budget[1]>30*1024*1024:raise HTTPException(413,'Expanded attachment limits exceeded')
            aid=str(uuid.uuid4());children=[];cidmap={}
            for ch in node.get('children',[]):
                saved=save(base64.b64decode(ch['data']),ch['name'],ch['result']);children.append(saved)
                if ch.get('cid'):cidmap[ch['cid']]=saved['id']
            soup=BeautifulSoup(node.get('html',''),'html.parser')
            for img in soup.find_all('img'):
                src=img.get('src','')
                if src.startswith('cid:') and src[4:] in cidmap:img['src']='/api/assets/'+cidmap[src[4:]]+'/image'
            raw=clean(str(soup));plain=text(raw);check_secrets(plain)
            if node.get('normalized'):
                payload=base64.b64decode(node['normalized']);raw='<img src="/api/assets/'+aid+'/image" alt="Uploaded image">'+raw
            warnings=node.get('warnings',[])
            for ch in children:warnings.extend(ch['warnings'])
            c.execute('INSERT INTO assets VALUES(?,?,?,?,?,?,?,?,?,?)',(aid,workspace,user['id'],Path(filename.replace('\\','/')).name[:180],node.get('mime','application/octet-stream'),payload,raw,plain,json.dumps(warnings),time.time()))
            for ch in children:c.execute('INSERT INTO asset_children VALUES(?,?)',(aid,ch['id']))
            return {'id':aid,'name':filename,'html':raw,'text':plain,'warnings':warnings,'children':children,'mime':node.get('mime')}
        saved=save(data,name,parsed)
        from .db import audit
        audit(c,user['id'],'asset.upload',saved['id'],workspace)
        return saved
