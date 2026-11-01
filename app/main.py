# Resolution Hub no-approval workflow update 3.0.1
import os,json,time,uuid,secrets,hashlib,sqlite3,logging,io
from pathlib import Path
from contextlib import asynccontextmanager
from urllib.parse import quote
from fastapi import FastAPI,Depends,HTTPException,Request,Response,UploadFile,File
from fastapi.responses import FileResponse,JSONResponse
from fastapi.staticfiles import StaticFiles
from .db import db,init,config,settings,audit,PERMISSIONS
from .security import identity,require,public_user,hash_password,verify,token_hash,valid_grants,preserve_admin,check_secrets,manage_target
from .content import clean,text,plain_html,image_ids,split_pairs
from .assets import upload,get_asset,expand
from . import models as M,ai
from . import mail

@asynccontextmanager
async def lifespan(app):init();yield
app=FastAPI(title='Resolution Hub',version='3.0.0',lifespan=lifespan)
# Limit streamed request bytes before multipart/JSON parsing, including missing Content-Length.
class BodyLimit:
    def __init__(self,app):self.app=app
    async def __call__(self,scope,receive,send):
        if scope['type']!='http':return await self.app(scope,receive,send)
        total=0;started=False
        async def bounded():
            nonlocal total
            message=await receive();total+=len(message.get('body',b''))
            if total>22*1024*1024:raise HTTPException(413,'Request body limit exceeded')
            return message
        await self.app(scope,bounded,send)
app.add_middleware(BodyLimit)
@app.middleware('http')
async def guards(request,call_next):
    if request.method not in ['GET','HEAD','OPTIONS']:
        origin=request.headers.get('origin','')
        allowed=os.getenv('ALLOWED_ORIGINS','http://127.0.0.1:8001,http://localhost:8001').split(',')
        if origin and origin not in allowed:return JSONResponse({'detail':'Origin not allowed'},status_code=403)
        if request.headers.get('sec-fetch-site')=='cross-site':return JSONResponse({'detail':'Cross-site request denied'},status_code=403)
    try:r=await call_next(request)
    except Exception:
        logging.exception('Unhandled application error');r=JSONResponse({'detail':'Unexpected error; see server request logs'},status_code=500)
    r.headers.update({'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','X-Frame-Options':'DENY','Referrer-Policy':'no-referrer','X-Request-ID':str(uuid.uuid4()),'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"})
    return r
@app.get('/health')
def health():
    with db() as c:c.execute('SELECT 1')
    return {'status':'ok','version':'3.0.0'}
@app.get('/api/branding')
def branding():
    with db() as c:cfg=settings(c)
    return {'instance_name':cfg['instance_name'],'logo':Path(os.getenv('DATABASE_PATH','data/hub-v3.db')).parent.joinpath('logo.png').exists()}
@app.get('/api/logo')
def logo():
    p=Path(os.getenv('DATABASE_PATH','data/hub-v3.db')).parent/'logo.png'
    if not p.exists():raise HTTPException(404,'No logo configured')
    return FileResponse(p,media_type='image/png')

def throttle(user,action,limit):
    with db() as c:
        key='api:'+action+':'+user['id'];now=time.time()
        c.execute('DELETE FROM attempts WHERE created<?',(now-900,))
        if c.execute('SELECT count(*) FROM attempts WHERE username=? AND created>?',(key,now-60)).fetchone()[0]>=limit:raise HTTPException(429,'Request rate limit reached')
        c.execute('INSERT INTO attempts(ip,username,created) VALUES(?,?,?)',('api',key,now))

@app.post('/api/auth/login')
def login(body:M.Login,request:Request,response:Response):
    ip=request.client.host if request.client else 'unknown';name=body.username.strip().lower();now=time.time()
    with db() as c:
        c.execute('DELETE FROM attempts WHERE created<?',(now-900,))
        n=c.execute("SELECT count(*) FROM attempts WHERE created>? AND ip!='api' AND (ip=? OR username=?)",(now-900,ip,name)).fetchone()[0]
        if n>=10:raise HTTPException(429,'Too many sign-in attempts. Contact your administrator or retry after the throttle window.')
        row=c.execute('SELECT * FROM users WHERE username=?',(name,)).fetchone()
        # Constant-cost dummy verification for unknown accounts.
        dummy='pbkdf2_sha256$600000$'+'00'*16+'$'+'00'*32
        good=verify(body.password,row['password'] if row else dummy)
        if not row or not good or not row['active']:
            c.execute('INSERT INTO attempts(ip,username,created) VALUES(?,?,?)',(ip,name,now));c.commit();raise HTTPException(401,'Invalid username or password')
        raw=secrets.token_urlsafe(48);csrf=hashlib.sha256(('csrf:'+raw).encode()).hexdigest()
        c.execute('DELETE FROM sessions WHERE user_id=? AND created<?',(row['id'],now-48*3600))
        c.execute('INSERT INTO sessions VALUES(?,?,?,?,?)',(token_hash(raw),row['id'],token_hash(csrf),now,now));audit(c,row['id'],'auth.login')
        cfg=settings(c)
    response.set_cookie('rh_session',raw,httponly=True,secure=os.getenv('COOKIE_SECURE','true')=='true',samesite='strict',max_age=cfg['absolute_hours']*3600,path='/')
    return {'csrf':csrf,'must_change':bool(row['must_change'])}
@app.get('/api/me')
def me(request:Request,user=Depends(identity)):
    csrf=hashlib.sha256(('csrf:'+request.cookies.get('rh_session','')).encode()).hexdigest()
    with db() as c:
        c.execute('UPDATE sessions SET csrf=? WHERE digest=?',(token_hash(csrf),user['digest']));cfg=settings(c)
    return {'user':public_user(user),'csrf':csrf,'workspaces':[w for w in config()['workspaces'] if '*' in user['workspaces'] or w['id'] in user['workspaces']],'instance_name':cfg['instance_name'],'provider':cfg['provider']}
@app.post('/api/auth/logout')
def logout(response:Response,user=Depends(identity)):
    with db() as c:c.execute('DELETE FROM sessions WHERE digest=?',(user['digest'],));audit(c,user['id'],'auth.logout')
    response.delete_cookie('rh_session',path='/');return {'ok':True}
@app.post('/api/auth/password')
def password(body:M.Password,response:Response,user=Depends(identity)):
    with db() as c:
        row=c.execute('SELECT password FROM users WHERE id=?',(user['id'],)).fetchone()
        if not verify(body.current_password,row[0]):raise HTTPException(400,'Current password is incorrect')
        if verify(body.new_password,row[0]):raise HTTPException(422,'Choose a different password')
        c.execute('UPDATE users SET password=?,must_change=0 WHERE id=?',(hash_password(body.new_password),user['id']));c.execute('DELETE FROM sessions WHERE user_id=?',(user['id'],));audit(c,user['id'],'auth.password_change')
    response.delete_cookie('rh_session',path='/');return {'ok':True,'notice':'Password changed; all sessions revoked. Sign in again.'}

GENERIC_RESET_NOTICE='If an account with a registered email exists, a reset link has been sent. Check your inbox.'
@app.post('/api/auth/forgot')
def forgot_password(body:M.ForgotRequest,request:Request):
    """Email-based reset request. Always returns the same generic response so the
    endpoint cannot be used to enumerate usernames or registered emails."""
    ip=request.client.host if request.client else 'unknown';name=body.username.strip().lower();now=time.time()
    with db() as c:
        c.execute('DELETE FROM attempts WHERE created<?',(now-900,))
        # Throttle reset requests per IP/username to limit email flooding.
        n=c.execute("SELECT count(*) FROM attempts WHERE created>? AND ip!='api' AND username=? AND ip=?",(now-900,'reset:'+name,ip)).fetchone()[0]
        if n>=5:return {'ok':True,'notice':GENERIC_RESET_NOTICE}
        c.execute('INSERT INTO attempts(ip,username,created) VALUES(?,?,?)',(ip,'reset:'+name,now))
        row=c.execute('SELECT id,username,email,active FROM users WHERE username=?',(name,)).fetchone()
        if row and row['active'] and (row['email'] or '').strip():
            token=secrets.token_urlsafe(32);minutes=int(os.getenv('RESET_TOKEN_MINUTES','30'))
            # Invalidate prior outstanding tokens for this user, then store the hash only.
            c.execute('DELETE FROM password_resets WHERE user_id=?',(row['id'],))
            c.execute('INSERT INTO password_resets(token_hash,user_id,created,expires,used) VALUES(?,?,?,?,0)',(token_hash(token),row['id'],now,now+minutes*60))
            audit(c,row['id'],'auth.reset_request')
            c.commit()
            mail.send_reset_email(row['email'],row['username'],token)
    return {'ok':True,'notice':GENERIC_RESET_NOTICE}
@app.post('/api/auth/reset')
def reset_with_token(body:M.ResetPassword,response:Response):
    """Complete a password reset using a one-time, time-limited token."""
    now=time.time();digest=token_hash(body.token.strip())
    with db() as c:
        r=c.execute('SELECT * FROM password_resets WHERE token_hash=?',(digest,)).fetchone()
        if not r or r['used'] or r['expires']<now:raise HTTPException(400,'This reset link is invalid or has expired. Request a new one.')
        c.execute('UPDATE users SET password=?,must_change=0 WHERE id=?',(hash_password(body.new_password),r['user_id']))
        c.execute('UPDATE password_resets SET used=1 WHERE token_hash=?',(digest,))
        c.execute('DELETE FROM sessions WHERE user_id=?',(r['user_id'],))
        audit(c,r['user_id'],'auth.reset_complete')
    response.delete_cookie('rh_session',path='/')
    return {'ok':True,'notice':'Password reset. All sessions were revoked. Sign in with your new password.'}
@app.patch('/api/profile')
def profile(body:M.Profile,user=Depends(identity)):
    with db() as c:c.execute('UPDATE users SET display_name=? WHERE id=?',(body.display_name.strip(),user['id']));audit(c,user['id'],'profile.update')
    return {'ok':True}

@app.get('/api/admin/users')
def users(user=Depends(identity)):
    require(user,'users.manage')
    with db() as c:return [dict(r)|{'workspaces':json.loads(r['workspaces'])} for r in c.execute('SELECT id,username,display_name,role,workspaces,active,must_change,email FROM users ORDER BY username')]
@app.post('/api/admin/users')
def create_user(body:M.UserCreate,user=Depends(identity)):
    require(user,'users.manage');valid_grants(body.workspaces)
    # Only an existing Administrator can assign the protected Administrator role.
    if body.role=='Administrator' and user['role']!='Administrator':raise HTTPException(403,'Only Administrator can assign Administrator')
    temp=secrets.token_urlsafe(20);uid=str(uuid.uuid4())
    with db() as c:
        role=c.execute('SELECT permissions FROM roles WHERE name=?',(body.role,)).fetchone()
        if not role:raise HTTPException(422,'Unknown role')
        if user['role']!='Administrator' and (set(json.loads(role[0]))-set(user['permissions']) or ('*' not in user['workspaces'] and set(body.workspaces)-set(user['workspaces']))):raise HTTPException(403,'Cannot delegate permissions or workspaces you do not hold')
        try:c.execute('INSERT INTO users(id,username,display_name,password,role,workspaces,active,must_change,created,email) VALUES(?,?,?,?,?,?,?,?,?,?)',(uid,body.username.lower(),body.display_name,hash_password(temp),body.role,json.dumps(body.workspaces),1,1,time.time(),(body.email or '').strip().lower()))
        except sqlite3.IntegrityError:raise HTTPException(409,'Username already exists')
        audit(c,user['id'],'user.create',uid)
    return {'id':uid,'temporary_password':temp,'notice':'Shown once. Deliver securely; user must change it on first login.'}
@app.patch('/api/admin/users/{uid}')
def update_user(uid:str,body:M.UserUpdate,user=Depends(identity)):
    require(user,'users.manage');valid_grants(body.workspaces)
    with db() as c:
        old=manage_target(c,user,uid);role=c.execute('SELECT permissions FROM roles WHERE name=?',(body.role,)).fetchone()
        if not old:raise HTTPException(404,'User not found')
        if not role:raise HTTPException(422,'Unknown role')
        if user['role']!='Administrator':
            if old['role']=='Administrator' or body.role=='Administrator' or set(json.loads(role[0]))-set(user['permissions']) or ('*' not in user['workspaces'] and set(body.workspaces)-set(user['workspaces'])):raise HTTPException(403,'Delegation exceeds your privileges')
        preserve_admin(c,uid,body.role,body.active)
        c.execute('UPDATE users SET role=?,workspaces=?,active=?,email=? WHERE id=?',(body.role,json.dumps(body.workspaces),int(body.active),(body.email or '').strip().lower(),uid));c.execute('DELETE FROM sessions WHERE user_id=?',(uid,));audit(c,user['id'],'user.access_update',uid)
    return {'ok':True,'notice':'Access updated; sessions revoked.'}
@app.post('/api/admin/users/{uid}/reset-password')
def reset_password(uid:str,user=Depends(identity)):
    require(user,'users.manage');temp=secrets.token_urlsafe(20)
    with db() as c:
        old=manage_target(c,user,uid)
        if not old:raise HTTPException(404,'User not found')
        if old['role']=='Administrator' and user['role']!='Administrator':raise HTTPException(403,'Cannot reset an Administrator')
        c.execute('UPDATE users SET password=?,must_change=1 WHERE id=?',(hash_password(temp),uid));c.execute('DELETE FROM sessions WHERE user_id=?',(uid,));audit(c,user['id'],'user.password_reset',uid)
    return {'temporary_password':temp,'notice':'Shown once. All sessions revoked; password change required.'}
@app.post('/api/admin/users/{uid}/revoke')
def revoke(uid:str,user=Depends(identity)):
    require(user,'users.manage')
    with db() as c:
        old=manage_target(c,user,uid)
        if not old:raise HTTPException(404,'User not found')
        if old['role']=='Administrator' and user['role']!='Administrator':raise HTTPException(403,'Cannot revoke Administrator sessions')
        c.execute('DELETE FROM sessions WHERE user_id=?',(uid,));audit(c,user['id'],'user.sessions_revoke',uid)
    return {'ok':True}
@app.get('/api/admin/roles')
def roles(user=Depends(identity)):
    if not any(p in user['permissions'] for p in ['roles.manage','users.manage']):raise HTTPException(403,'Role access denied')
    with db() as c:return {'permissions':PERMISSIONS,'roles':[{'name':r['name'],'permissions':json.loads(r['permissions'])} for r in c.execute('SELECT * FROM roles')]}
@app.put('/api/admin/roles')
def save_role(body:M.Role,user=Depends(identity)):
    require(user,'roles.manage')
    if body.name=='Administrator':raise HTTPException(403,'Administrator is a protected full-permission role')
    if set(body.permissions)-set(PERMISSIONS):raise HTTPException(422,'Unknown permission')
    if set(body.permissions)-set(user['permissions']):raise HTTPException(403,'Cannot grant permissions you do not hold')
    with db() as c:
        old=c.execute('SELECT permissions FROM roles WHERE name=?',(body.name,)).fetchone()
        if old and set(json.loads(old[0]))-set(user['permissions']):raise HTTPException(403,'Cannot edit a more privileged role')
        c.execute('INSERT INTO roles VALUES(?,?) ON CONFLICT(name) DO UPDATE SET permissions=excluded.permissions',(body.name,json.dumps(sorted(set(body.permissions)))));c.execute('DELETE FROM sessions WHERE user_id IN (SELECT id FROM users WHERE role=?)',(body.name,));audit(c,user['id'],'role.save',body.name)
    return {'ok':True,'notice':'Role saved; affected sessions revoked.'}
@app.delete('/api/admin/roles/{name}')
def delete_role(name:str,user=Depends(identity)):
    require(user,'roles.manage')
    if name=='Administrator':raise HTTPException(403,'Protected role')
    with db() as c:
        if c.execute('SELECT 1 FROM users WHERE role=?',(name,)).fetchone():raise HTTPException(409,'Reassign users before deleting this role')
        c.execute('DELETE FROM roles WHERE name=?',(name,));audit(c,user['id'],'role.delete',name)
    return {'ok':True}

@app.get('/api/admin/settings')
def get_settings(user=Depends(identity)):
    require(user,'settings.manage')
    with db() as c:r=c.execute('SELECT * FROM settings WHERE id=1').fetchone()
    return {'version':r['version'],'settings':json.loads(r['body']),'api_key_configured':bool(os.getenv('OPENAI_API_KEY')),'server_external_ai':os.getenv('ALLOW_EXTERNAL_AI')=='true','allowed_hosts':os.getenv('AI_ALLOWED_HOSTS',''),'ocr_enabled':os.getenv('OCR_ENABLED')=='true','scan_mode':os.getenv('UPLOAD_SCAN','off')}
@app.put('/api/admin/settings')
def save_settings(body:M.SettingsUpdate,user=Depends(identity)):
    require(user,'settings.manage');cfg=body.model_dump(exclude={'expected_version'})
    if cfg['provider']!='evidence':ai.endpoint(cfg)
    if os.getenv('APP_ENV')=='production' and not cfg['require_scan']:raise HTTPException(422,'Cannot disable required production scanning')
    with db() as c:
        r=c.execute('UPDATE settings SET version=version+1,body=? WHERE id=1 AND version=?',(json.dumps(cfg),body.expected_version))
        if r.rowcount!=1:raise HTTPException(409,'Settings changed; reload')
        audit(c,user['id'],'settings.update')
    return {'ok':True}
@app.post('/api/admin/ai-test')
def ai_test(user=Depends(identity)):
    require(user,'settings.manage')
    with db() as c:cfg=settings(c)
    if cfg['provider']=='evidence':return {'ok':True,'notice':'Evidence-only mode; no AI request made'}
    result=ai.call([{'role':'user','content':'Synthetic connectivity test. Reply OK.'}],cfg)
    return {'ok':True,'response':result[:300]}
@app.post('/api/admin/logo')
async def upload_logo(file:UploadFile=File(...),user=Depends(identity)):
    require(user,'settings.manage');data=await file.read(2000001)
    if len(data)>2000000 or not data.startswith(b'\x89PNG\r\n\x1a\n'):raise HTTPException(422,'Use a PNG under 2 MB')
    from PIL import Image
    try:
        im=Image.open(io.BytesIO(data));im.load()
        if im.width*im.height>4000000:raise ValueError()
        im.thumbnail((600,600));buf=io.BytesIO();im.save(buf,format='PNG')
    except Exception:raise HTTPException(422,'Invalid or oversized PNG')
    p=Path(os.getenv('DATABASE_PATH','data/hub-v3.db')).parent/'logo.png';tmp=p.with_suffix('.tmp');tmp.write_bytes(buf.getvalue());tmp.replace(p)
    with db() as c:audit(c,user['id'],'branding.logo')
    return {'ok':True}
@app.delete('/api/admin/logo')
def reset_logo(user=Depends(identity)):
    require(user,'settings.manage');(Path(os.getenv('DATABASE_PATH','data/hub-v3.db')).parent/'logo.png').unlink(missing_ok=True);return {'ok':True}

@app.post('/api/workspaces/{workspace}/assets')
async def upload_asset(workspace:str,file:UploadFile=File(...),user=Depends(identity)):
    throttle(user,'upload',20)
    with db() as c:cap=settings(c)['upload_mb']*1024*1024
    data=await file.read(cap+1)
    from starlette.concurrency import run_in_threadpool
    return await run_in_threadpool(upload,data,file.filename or 'file',workspace,user)
@app.get('/api/assets/{aid}/image')
def asset_image(aid:str,user=Depends(identity)):
    with db() as c:a=get_asset(c,aid,user)
    if a['mime']!='image/png':raise HTTPException(415,'Not an image')
    return Response(a['body'],media_type='image/png')
@app.get('/api/assets/{aid}/download')
def asset_download(aid:str,user=Depends(identity)):
    with db() as c:a=get_asset(c,aid,user)
    return Response(a['body'],media_type='application/octet-stream',headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(a['name'])})
@app.post('/api/workspaces/{workspace}/extract')
def extract(workspace:str,body:M.Extract,user=Depends(identity)):
    require(user,'knowledge.create',workspace)
    with db() as c:
        cfg=settings(c);assets=[get_asset(c,x,user,workspace,own=True) for x in body.asset_ids]
        ids=expand(c,body.asset_ids);all_assets=[get_asset(c,x,user,workspace,own=True) for x in ids]
    pairs=[]
    for a in all_assets:
        if not a['text'].strip():continue
        rows=ai.extract_pairs(a['html'],a['name'],cfg) if body.use_ai and cfg['ai_extract'] else split_pairs(a['html'],a['name'])
        for r in rows:r['asset_ids']=body.asset_ids;r['warnings']+=json.loads(a['warnings'])
        pairs+=rows
    if body.use_ai and not cfg['ai_extract']:raise HTTPException(403,'AI-assisted extraction is disabled by the administrator')
    return {'pairs':pairs[:30],'sources':[{'id':a['id'],'name':a['name'],'html':a['html'],'warnings':json.loads(a['warnings'])} for a in assets],'warnings':[] if pairs else ['No readable text found. Review images manually or enable approved OCR/vision.']}

def record(c,kid,user,permission='knowledge.read'):
    r=c.execute('SELECT * FROM knowledge WHERE id=?',(kid,)).fetchone()
    if not r:raise HTTPException(404,'Knowledge not found')
    require(user,permission,r['workspace']);return dict(r)
def snapshot(c,k,user,note=''):
    c.execute('INSERT INTO versions(knowledge_id,version,body,actor,note,created) VALUES(?,?,?,?,?,?)',(k['id'],k['version'],json.dumps(k),user['id'],note,time.time()))
def save_knowledge(c,workspace,body,user,kid=None):
    require(user,'knowledge.edit' if kid else 'knowledge.create',workspace)
    issue=clean(body.issue_html);resolution=clean(body.resolution_html);it=text(issue);rt=text(resolution)
    if len(it)<5 and not image_ids(issue):raise HTTPException(422,'Issue needs readable text or an uploaded image')
    if len(it)>100000 or len(rt)>100000:raise HTTPException(413,'Knowledge text limit exceeded')
    check_secrets(it+'\n'+rt+'\n'+body.environment)
    assets=set(body.asset_ids)|image_ids(issue)|image_ids(resolution)
    existing=None
    if kid:
        existing=record(c,kid,user,'knowledge.edit')
        if existing['workspace']!=workspace:raise HTTPException(403,'Cannot move knowledge between workspaces')
        if existing['editor']!=user['id'] and existing['author']!=user['id'] and 'knowledge.review' not in user['permissions']:raise HTTPException(403,'Only author/editor or reviewer can edit this record')
    old_assets={r[0] for r in c.execute('SELECT asset_id FROM knowledge_assets WHERE knowledge_id=?',(kid or '',))}
    for aid in assets:get_asset(c,aid,user,workspace,own=aid not in old_assets)
    assets=expand(c,assets)
    digest=hashlib.sha256((it.strip().lower()+'\n'+rt.strip().lower()).encode()).hexdigest();now=time.time();status='published' if rt else 'unresolved'
    try:
        if kid:
            r=c.execute('UPDATE knowledge SET issue_html=?,resolution_html=?,issue_text=?,resolution_text=?,environment=?,status=?,editor=?,version=version+1,digest=?,updated=? WHERE id=? AND version=?',(issue,resolution,it,rt,body.environment,status,user['id'],digest,now,kid,body.expected_version))
            if r.rowcount!=1:raise HTTPException(409,'Version conflict; reload before editing')
        else:
            kid=str(uuid.uuid4());c.execute('INSERT INTO knowledge VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(kid,workspace,issue,resolution,it,rt,body.environment,status,user['id'],user['id'],1,digest,now,now))
    except sqlite3.IntegrityError:raise HTTPException(409,'Duplicate issue/resolution in this workspace')
    c.execute('DELETE FROM knowledge_assets WHERE knowledge_id=?',(kid,))
    for aid in assets:c.execute('INSERT INTO knowledge_assets VALUES(?,?)',(kid,aid))
    c.execute('DELETE FROM knowledge_fts WHERE id=?',(kid,));c.execute('INSERT INTO knowledge_fts VALUES(?,?)',(kid,it+'\n'+rt+'\n'+body.environment))
    k=dict(c.execute('SELECT * FROM knowledge WHERE id=?',(kid,)).fetchone());snapshot(c,k,user);audit(c,user['id'],'knowledge.save',kid,workspace);return k
@app.post('/api/workspaces/{workspace}/knowledge')
def create_knowledge(workspace:str,body:M.Knowledge,user=Depends(identity)):
    with db() as c:return save_knowledge(c,workspace,body,user)
@app.put('/api/workspaces/{workspace}/knowledge/{kid}')
def edit_knowledge(workspace:str,kid:str,body:M.Knowledge,user=Depends(identity)):
    with db() as c:return save_knowledge(c,workspace,body,user,kid)
@app.post('/api/workspaces/{workspace}/import')
def import_pairs(workspace:str,body:M.Import,user=Depends(identity)):
    require(user,'knowledge.create',workspace)
    if not all(p.confirmed for p in body.pairs):raise HTTPException(422,'Review and confirm every submitted pairing')
    with db() as c:
        saved=[save_knowledge(c,workspace,p,user) for p in body.pairs];audit(c,user['id'],'knowledge.import',str(len(saved)),workspace)
    return {'saved':saved}
@app.get('/api/workspaces/{workspace}/knowledge')
def library(workspace:str,q:str='',status:str='',offset:int=0,user=Depends(identity)):
    require(user,'knowledge.read',workspace)
    with db() as c:
        rows=c.execute("SELECT id,workspace,issue_text,resolution_text,environment,status,author,editor,version,updated FROM knowledge WHERE workspace=? AND (issue_text LIKE ? OR resolution_text LIKE ?) AND (?='' OR status=?) ORDER BY updated DESC LIMIT 50 OFFSET ?",(workspace,'%'+q[:200]+'%','%'+q[:200]+'%',status,status,max(0,offset))).fetchall()
    return [dict(r) for r in rows]
@app.get('/api/knowledge/{kid}')
def knowledge_detail(kid:str,user=Depends(identity)):
    with db() as c:
        k=record(c,kid,user);k['assets']=[dict(r) for r in c.execute('SELECT a.id,a.name,a.mime,a.warnings FROM assets a JOIN knowledge_assets ka ON ka.asset_id=a.id WHERE ka.knowledge_id=?',(kid,))];return k
@app.get('/api/knowledge/{kid}/versions')
def versions(kid:str,user=Depends(identity)):
    with db() as c:record(c,kid,user);return [dict(r) for r in c.execute('SELECT * FROM versions WHERE knowledge_id=? ORDER BY version DESC',(kid,))]
@app.post('/api/knowledge/{kid}/review')
def review(kid:str,body:M.Review,user=Depends(identity)):
    with db() as c:
        k=record(c,kid,user,'knowledge.review')
        if body.status=='published':
            if not k['resolution_text'].strip():raise HTTPException(422,'A resolution is required before making a record searchable')
        r=c.execute('UPDATE knowledge SET status=?,version=version+1,updated=? WHERE id=? AND version=?',(body.status,time.time(),kid,body.expected_version))
        if r.rowcount!=1:raise HTTPException(409,'Version conflict')
        k=dict(c.execute('SELECT * FROM knowledge WHERE id=?',(kid,)).fetchone());snapshot(c,k,user,body.note);audit(c,user['id'],'knowledge.'+body.status,kid,k['workspace']);return k

@app.post('/api/workspaces/{workspace}/chat')
def chat(workspace:str,body:M.Chat,request:Request,user=Depends(identity)):
    require(user,'solve',workspace);throttle(user,'chat',30);raw=clean(body.html);value=text(raw);check_secrets(value)
    if not value and not body.asset_ids and not image_ids(raw):raise HTTPException(422,'Enter a message or attach a file')
    with db() as c:
        cfg=settings(c);cid=body.conversation_id
        if cid and not c.execute('SELECT 1 FROM conversations WHERE id=? AND owner=? AND workspace=?',(cid,user['id'],workspace)).fetchone():raise HTTPException(404,'Conversation not found')
        ids=set(body.asset_ids)|image_ids(raw)
        for aid in ids:get_asset(c,aid,user,workspace,own=True)
        ids=expand(c,ids);assets=[get_asset(c,x,user,workspace,own=True) for x in ids]
        attached='\n'.join(a['name']+':\n'+a['text'] for a in assets if a['text'])[:40000]
        issue=value+'\n'+attached
        if len(issue)>60000:raise HTTPException(413,'Message context too large')
        check_secrets(issue)
        history=[{'role':r['role'],'text':r['text'][:6000]} for r in c.execute("SELECT role,text FROM messages WHERE conversation_id=? ORDER BY created DESC LIMIT 8",(cid or '',))][::-1]
        sources=ai.retrieve(c,workspace,'\n'.join(h['text'] for h in [x for x in history if x['role']=='user'][-2:])+'\n'+issue)
        images=[a['body'] for a in assets if a['mime']=='image/png']
        previous_ids=set()
        for old in c.execute("SELECT assets FROM messages WHERE conversation_id=? AND role='user' ORDER BY created DESC LIMIT 6",(cid or '',)):
            previous_ids.update(json.loads(old['assets']))
        for aid in sorted(previous_ids-ids):
            previous=get_asset(c,aid,user,workspace,own=True)
            if previous['mime']=='image/png':images.append(previous['body'])
        warnings=[w for a in assets for w in json.loads(a['warnings'])]
        if images and not cfg['vision']:warnings.append('Images retained, but not sent for visual analysis; vision is disabled.')
        if len(images)>4:warnings.append('Only the first four images are included in this model request.')
    result,mode=ai.answer(issue,history,sources,images,cfg)
    user=identity(request);require(user,'solve',workspace)
    with db() as c:
        # Source approval/version must still be current before answer persistence.
        for s in sources:
            r=c.execute('SELECT status,version FROM knowledge WHERE id=?',(s['knowledge_id'],)).fetchone()
            if not r or r['status']!='published' or r['version']!=s['version']:raise HTTPException(409,'Evidence changed during generation; retry')
        if not cid:
            cid=str(uuid.uuid4());c.execute('INSERT INTO conversations VALUES(?,?,?,?,?,?)',(cid,workspace,user['id'],(value or 'Attached email')[:160],time.time(),time.time()))
        elif not c.execute('SELECT 1 FROM conversations WHERE id=? AND owner=?',(cid,user['id'])).fetchone():raise HTTPException(409,'Conversation removed; start a new one')
        mid=str(uuid.uuid4());c.execute('INSERT INTO messages VALUES(?,?,?,?,?,?,?,?,?)',(str(uuid.uuid4()),cid,'user',raw,issue,json.dumps(sorted(ids)),'[]','user',time.time()))
        c.execute('INSERT INTO messages VALUES(?,?,?,?,?,?,?,?,?)',(mid,cid,'assistant',plain_html(result),result,'[]',json.dumps(sources),mode,time.time()));c.execute('UPDATE conversations SET updated=? WHERE id=?',(time.time(),cid));audit(c,user['id'],'chat.answer',mid,workspace)
    return {'conversation_id':cid,'message_id':mid,'text':result,'sources':sources,'warnings':list(dict.fromkeys(warnings)),'mode':mode}
@app.get('/api/workspaces/{workspace}/history')
def history(workspace:str,offset:int=0,user=Depends(identity)):
    require(user,'solve',workspace)
    with db() as c:return [dict(r) for r in c.execute('SELECT * FROM conversations WHERE workspace=? AND owner=? ORDER BY updated DESC LIMIT 50 OFFSET ?',(workspace,user['id'],max(0,offset)))]
@app.get('/api/conversations/{cid}')
def conversation(cid:str,user=Depends(identity)):
    with db() as c:
        r=c.execute('SELECT * FROM conversations WHERE id=? AND owner=?',(cid,user['id'])).fetchone()
        if not r:raise HTTPException(404,'Conversation not found')
        require(user,'solve',r['workspace'])
        return {'conversation':dict(r),'messages':[dict(m) for m in c.execute('SELECT * FROM messages WHERE conversation_id=? ORDER BY created',(cid,))]}
@app.post('/api/messages/{mid}/feedback')
def feedback(mid:str,body:M.Feedback,user=Depends(identity)):
    with db() as c:
        r=c.execute("SELECT co.workspace FROM messages m JOIN conversations co ON co.id=m.conversation_id WHERE m.id=? AND m.role='assistant' AND co.owner=?",(mid,user['id'])).fetchone()
        if not r:raise HTTPException(404,'Answer not found')
        require(user,'solve',r['workspace']);c.execute('INSERT INTO feedback(message_id,user_id,useful,created) VALUES(?,?,?,?)',(mid,user['id'],int(body.useful),time.time()));return {'ok':True}
@app.get('/api/workspaces/{workspace}/dashboard')
def dashboard(workspace:str,user=Depends(identity)):
    if 'knowledge.read' not in user['permissions'] and 'solve' not in user['permissions']:raise HTTPException(403,'Workspace access denied')
    require(user,'knowledge.read' if 'knowledge.read' in user['permissions'] else 'solve',workspace)
    with db() as c:
        counts={r['status']:r['n'] for r in c.execute('SELECT status,count(*) n FROM knowledge WHERE workspace=? GROUP BY status',(workspace,))} if 'knowledge.read' in user['permissions'] else {}
        conversations=c.execute('SELECT count(*) FROM conversations WHERE workspace=? AND owner=?',(workspace,user['id'])).fetchone()[0]
    return {'counts':counts,'conversations':conversations}
@app.get('/api/admin/audit')
def audit_list(offset:int=0,user=Depends(identity)):
    require(user,'audit.read')
    with db() as c:return [dict(r) for r in c.execute('SELECT * FROM audit ORDER BY id DESC LIMIT 100 OFFSET ?',(max(0,offset),))]
@app.post('/api/admin/purge-history')
def purge(user=Depends(identity)):
    require(user,'maintenance.manage')
    with db() as c:
        cutoff=time.time()-settings(c)['retention_days']*86400;r=c.execute('DELETE FROM conversations WHERE updated<?',(cutoff,));audit(c,user['id'],'history.purge',str(r.rowcount));return {'deleted':r.rowcount,'notice':'Only investigation history and feedback purged. Knowledge, attachments, audit and backups remain.'}
@app.post('/api/admin/reindex')
def reindex(user=Depends(identity)):
    require(user,'maintenance.manage')
    with db() as c:
        c.execute('DELETE FROM knowledge_fts');rows=c.execute('SELECT * FROM knowledge').fetchall()
        for r in rows:c.execute('INSERT INTO knowledge_fts VALUES(?,?)',(r['id'],r['issue_text']+'\n'+r['resolution_text']+'\n'+r['environment']))
        audit(c,user['id'],'knowledge.reindex',str(len(rows)));return {'indexed':len(rows)}
@app.get('/api/admin/export')
def export(user=Depends(identity)):
    require(user,'maintenance.manage')
    with db() as c:
        rows=[dict(r) for r in c.execute('SELECT * FROM knowledge')];audit(c,user['id'],'knowledge.export',str(len(rows)))
    return {'schema_version':3,'instance':config()['instance_id'],'knowledge':rows,'notice':'Knowledge-only export; not a full backup. Attachments are not embedded.'}
app.mount('/static',StaticFiles(directory=Path(__file__).parent/'static'),name='static')
@app.get('/')
def home():return FileResponse(Path(__file__).parent/'static/index.html')
