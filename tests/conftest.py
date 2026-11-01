import os,json,time,uuid
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
PASSWORD='Synthetic-password-2026!'
@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.chdir(Path(__file__).resolve().parents[1]);monkeypatch.setenv('DATABASE_PATH',str(tmp_path/'test.db'));monkeypatch.setenv('INSTANCE_CONFIG','config/instance.json');monkeypatch.setenv('APP_ENV','development');monkeypatch.setenv('COOKIE_SECURE','false');monkeypatch.setenv('CHAT_PROVIDER','evidence');monkeypatch.setenv('UPLOAD_SCAN','off');monkeypatch.setenv('OCR_ENABLED','false');monkeypatch.setenv('ALLOWED_ORIGINS','http://testserver');monkeypatch.setenv('ALLOW_EXTERNAL_AI','false')
    from app.db import config,init,db
    config.cache_clear();init()
    from app.security import hash_password
    pw=hash_password(PASSWORD)
    with db() as c:
        for name,role,ws in [('admin','Administrator',['*']),('engineer','Engineer',['inhouse']),('reviewer','Reviewer',['inhouse']),('reader','Reader',['inhouse']),('outsider','Reader',['rpa'])]:
            c.execute('INSERT INTO users(id,username,display_name,password,role,workspaces,active,must_change,created) VALUES(?,?,?,?,?,?,?,?,?)',(name,name,name,pw,role,json.dumps(ws),1,0,time.time()))
    from app.main import app
    with TestClient(app) as c:yield c
    config.cache_clear()
def auth(c,name='engineer',password=PASSWORD):
    r=c.post('/api/auth/login',json={'username':name,'password':password});assert r.status_code==200,r.text
    return {'X-CSRF-Token':r.json()['csrf']}
