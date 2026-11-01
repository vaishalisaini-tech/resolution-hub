import os,json,time,hashlib,secrets,re
from fastapi import Request,HTTPException
from .db import db,config,settings

def hash_password(password):
    if not 15<=len(password)<=128:raise HTTPException(422,'Password must contain 15 to 128 characters')
    salt=secrets.token_bytes(16);iterations=600000
    h=hashlib.pbkdf2_hmac('sha256',password.encode(),salt,iterations)
    return f'pbkdf2_sha256${iterations}${salt.hex()}${h.hex()}'
def verify(password,stored):
    if len(password)>128:return False
    try:
        alg,it,salt,digest=stored.split('$');assert alg=='pbkdf2_sha256'
        return secrets.compare_digest(hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),int(it)).hex(),digest)
    except Exception:return False
def token_hash(token):return hashlib.sha256(token.encode()).hexdigest()
def identity(request:Request):
    raw=request.cookies.get('rh_session','')
    with db() as c:
        r=c.execute('SELECT s.*,u.username,u.display_name,u.role,u.workspaces,u.active,u.must_change FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.digest=?',(token_hash(raw),)).fetchone()
        if not r or not r['active']:raise HTTPException(401,'Sign in required')
        cfg=settings(c);t=time.time()
        if t-r['last_seen']>cfg['idle_minutes']*60 or t-r['created']>cfg['absolute_hours']*3600:
            c.execute('DELETE FROM sessions WHERE digest=?',(r['digest'],));c.commit();raise HTTPException(401,'Session expired')
        if request.method not in ['GET','HEAD','OPTIONS']:
            supplied=request.headers.get('x-csrf-token','')
            if not secrets.compare_digest(token_hash(supplied),r['csrf']):raise HTTPException(403,'Invalid CSRF token; refresh and sign in again')
        if r['must_change'] and request.url.path not in ['/api/me','/api/auth/password','/api/auth/logout']:raise HTTPException(403,'Change your temporary password first')
        c.execute('UPDATE sessions SET last_seen=? WHERE digest=?',(t,r['digest']))
        user=dict(r);user['id']=r['user_id'];user['workspaces']=json.loads(r['workspaces']);user['permissions']=json.loads(c.execute('SELECT permissions FROM roles WHERE name=?',(r['role'],)).fetchone()[0]);return user
def require(user,permission,workspace=None):
    if permission not in user['permissions']:raise HTTPException(403,'Permission required: '+permission)
    if workspace:
        if workspace not in [w['id'] for w in config()['workspaces']]:raise HTTPException(404,'Unknown workspace')
        if '*' not in user['workspaces'] and workspace not in user['workspaces']:raise HTTPException(403,'Workspace access denied')
def public_user(u):return {k:u[k] for k in ['id','username','display_name','role','workspaces','permissions','must_change']}
def check_secrets(text):
    if re.search(r'-----BEGIN .*PRIVATE KEY-----|(?i:\b(?:password|passwd|api[_-]?key|access[_-]?token)\s*[:=]\s*[^\s<]{6,})',text):raise HTTPException(422,'Possible credential detected. Remove secrets before saving or sending.')
def valid_grants(grants):
    if not isinstance(grants,list) or not grants or set(grants)-({'*'}|{w['id'] for w in config()['workspaces']}):raise HTTPException(422,'Invalid workspace grants')
def preserve_admin(c,user_id,role,active):
    old=c.execute('SELECT role,active FROM users WHERE id=?',(user_id,)).fetchone()
    if old and old['role']=='Administrator' and old['active'] and (role!='Administrator' or not active):
        if c.execute("SELECT count(*) FROM users WHERE role='Administrator' AND active=1").fetchone()[0]<=1:raise HTTPException(409,'Cannot remove the last active Administrator')

def manage_target(c,user,uid):
    target=c.execute('SELECT u.*,r.permissions FROM users u JOIN roles r ON r.name=u.role WHERE u.id=?',(uid,)).fetchone()
    if not target:raise HTTPException(404,'User not found')
    if user['role']!='Administrator':
        if target['role']=='Administrator' or set(json.loads(target['permissions']))-set(user['permissions']):raise HTTPException(403,'Cannot manage a more privileged account')
        if '*' not in user['workspaces'] and set(json.loads(target['workspaces']))-set(user['workspaces']):raise HTTPException(403,'Cannot manage an account outside your workspace grants')
    return target
