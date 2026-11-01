import os,json,sqlite3,time,hashlib
from pathlib import Path
from contextlib import contextmanager
from functools import lru_cache
from dotenv import load_dotenv
load_dotenv()
@lru_cache(maxsize=1)
def config():
    c=json.loads(Path(os.getenv('INSTANCE_CONFIG','config/instance.json')).read_text())
    import re
    ids=[w['id'] for w in c['workspaces']]
    if not ids or len(ids)!=len(set(ids)) or any(not re.fullmatch('[a-z0-9-]{1,40}',x) for x in ids):raise RuntimeError('Invalid workspace IDs')
    return c
@contextmanager
def db():
    p=Path(os.getenv('DATABASE_PATH','data/hub-v3.db'));p.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(p,timeout=20);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON')
    try:yield c;c.commit()
    except Exception:c.rollback();raise
    finally:c.close()
PERMISSIONS=['solve','knowledge.read','knowledge.create','knowledge.edit','knowledge.review','users.manage','roles.manage','settings.manage','audit.read','maintenance.manage']
DEFAULTS={'Administrator':PERMISSIONS,'Engineer':['solve','knowledge.read','knowledge.create','knowledge.edit'],'Reviewer':['solve','knowledge.read','knowledge.review'],'Reader':['solve','knowledge.read']}
SETTINGS={'idle_minutes':30,'absolute_hours':12,'upload_mb':10,'retention_days':365,'instance_name':'','model':'','provider':'evidence','base_url':'','vision':False,'ai_extract':False,'require_scan':False}
def settings(c):
    return json.loads(c.execute('SELECT body FROM settings WHERE id=1').fetchone()[0])
def init():
    cfg=config()
    if os.getenv('APP_ENV')=='production':
        if os.getenv('COOKIE_SECURE','true').lower()!='true':raise RuntimeError('Production requires secure cookies')
        from urllib.parse import urlparse
        origins=os.getenv('ALLOWED_ORIGINS','').split(',')
        if not origins or any(urlparse(x).scheme!='https' or not urlparse(x).hostname or urlparse(x).path not in ['', '/'] for x in origins):raise RuntimeError('Production requires explicit HTTPS origins')
        if os.getenv('UPLOAD_SCAN')!='required':raise RuntimeError('Production requires UPLOAD_SCAN=required and scanner')
    with db() as c:
        tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if tables and 'meta' not in tables:raise RuntimeError('Use a NEW v3 database. See migration guide.')
        c.execute('PRAGMA journal_mode=WAL')
        c.executescript('''
        CREATE TABLE IF NOT EXISTS meta(id INTEGER PRIMARY KEY,instance TEXT NOT NULL,version INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS roles(name TEXT PRIMARY KEY,permissions TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,username TEXT UNIQUE COLLATE NOCASE NOT NULL,display_name TEXT NOT NULL,password TEXT NOT NULL,role TEXT NOT NULL REFERENCES roles(name),workspaces TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1,must_change INTEGER NOT NULL DEFAULT 1,created REAL NOT NULL,email TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS password_resets(token_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,created REAL NOT NULL,expires REAL NOT NULL,used INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS sessions(digest TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,csrf TEXT NOT NULL,created REAL NOT NULL,last_seen REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS attempts(id INTEGER PRIMARY KEY,ip TEXT NOT NULL,username TEXT NOT NULL,created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS settings(id INTEGER PRIMARY KEY CHECK(id=1),version INTEGER NOT NULL,body TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS assets(id TEXT PRIMARY KEY,workspace TEXT NOT NULL,owner TEXT NOT NULL REFERENCES users(id),name TEXT NOT NULL,mime TEXT NOT NULL,body BLOB NOT NULL,html TEXT NOT NULL,text TEXT NOT NULL,warnings TEXT NOT NULL,created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS asset_children(parent TEXT NOT NULL REFERENCES assets(id) ON DELETE CASCADE,child TEXT NOT NULL REFERENCES assets(id) ON DELETE CASCADE,PRIMARY KEY(parent,child));
        CREATE TABLE IF NOT EXISTS knowledge(id TEXT PRIMARY KEY,workspace TEXT NOT NULL,issue_html TEXT NOT NULL,resolution_html TEXT NOT NULL,issue_text TEXT NOT NULL,resolution_text TEXT NOT NULL,environment TEXT NOT NULL,status TEXT NOT NULL,author TEXT NOT NULL REFERENCES users(id),editor TEXT NOT NULL REFERENCES users(id),version INTEGER NOT NULL,digest TEXT NOT NULL,created REAL NOT NULL,updated REAL NOT NULL,UNIQUE(workspace,digest));
        CREATE TABLE IF NOT EXISTS knowledge_assets(knowledge_id TEXT NOT NULL REFERENCES knowledge(id) ON DELETE CASCADE,asset_id TEXT NOT NULL REFERENCES assets(id),PRIMARY KEY(knowledge_id,asset_id));
        CREATE TABLE IF NOT EXISTS versions(id INTEGER PRIMARY KEY,knowledge_id TEXT NOT NULL REFERENCES knowledge(id),version INTEGER NOT NULL,body TEXT NOT NULL,actor TEXT NOT NULL,note TEXT NOT NULL,created REAL NOT NULL,UNIQUE(knowledge_id,version));
        CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(id UNINDEXED,text);
        CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY,workspace TEXT NOT NULL,owner TEXT NOT NULL REFERENCES users(id),title TEXT NOT NULL,created REAL NOT NULL,updated REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY,conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,role TEXT NOT NULL,html TEXT NOT NULL,text TEXT NOT NULL,assets TEXT NOT NULL,sources TEXT NOT NULL,mode TEXT NOT NULL,created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS feedback(id INTEGER PRIMARY KEY,message_id TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,user_id TEXT NOT NULL,useful INTEGER NOT NULL,created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,actor TEXT NOT NULL,action TEXT NOT NULL,target TEXT NOT NULL,workspace TEXT NOT NULL,created REAL NOT NULL,previous TEXT NOT NULL,hash TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS knowledge_scope ON knowledge(workspace,status);
        CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id);
        ''')
        # Idempotent migration: add the email column to databases created before it existed.
        if 'email' not in {r[1] for r in c.execute("PRAGMA table_info(users)")}:
            c.execute("ALTER TABLE users ADD COLUMN email TEXT NOT NULL DEFAULT ''")
        row=c.execute('SELECT * FROM meta WHERE id=1').fetchone()
        if row and (row['instance']!=cfg['instance_id'] or row['version']!=3):raise RuntimeError('Instance/schema mismatch')
        c.execute('INSERT OR IGNORE INTO meta VALUES(1,?,3)',(cfg['instance_id'],))
        for role,ps in DEFAULTS.items():c.execute('INSERT OR IGNORE INTO roles VALUES(?,?)',(role,json.dumps(ps)))
        initial={**SETTINGS,'instance_name':cfg['instance_name'],'provider':os.getenv('CHAT_PROVIDER','evidence'),'model':os.getenv('CHAT_MODEL',''),'base_url':os.getenv('OPENAI_BASE_URL',''),'vision':os.getenv('VISION_ENABLED','false')=='true','ai_extract':os.getenv('AI_EXTRACT_ENABLED','false')=='true','require_scan':os.getenv('UPLOAD_SCAN')=='required'}
        c.execute('INSERT OR IGNORE INTO settings VALUES(1,1,?)',(json.dumps(initial),))
        used={r[0] for r in c.execute('SELECT workspace FROM knowledge UNION SELECT workspace FROM conversations UNION SELECT workspace FROM assets')}
        if used-{w['id'] for w in cfg['workspaces']}:raise RuntimeError('Cannot remove populated workspace IDs')
def audit(c,actor,action,target='',workspace=''):
    row=c.execute('SELECT hash FROM audit ORDER BY id DESC LIMIT 1').fetchone();prev=row[0] if row else '0'*64;t=time.time()
    h=hashlib.sha256(json.dumps([actor,action,target,workspace,t,prev],separators=(',',':')).encode()).hexdigest()
    c.execute('INSERT INTO audit(actor,action,target,workspace,created,previous,hash) VALUES(?,?,?,?,?,?,?)',(actor,action,target,workspace,t,prev,h))
