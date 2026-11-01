import time
from conftest import auth,PASSWORD
from app.db import db
from app import mail

def set_email(username,email):
    with db() as c:c.execute('UPDATE users SET email=? WHERE username=?',(email,username))

def latest_token(monkeypatch):
    captured={}
    def fake_send(to,user,token):captured['to']=to;captured['user']=user;captured['token']=token;return True
    monkeypatch.setattr(mail,'send_reset_email',fake_send)
    return captured

def test_forgot_generic_response_unknown_user(client):
    r=client.post('/api/auth/forgot',json={'username':'does-not-exist'})
    assert r.status_code==200
    assert 'reset link' in r.json()['notice'].lower()

def test_forgot_no_email_no_leak(client,monkeypatch):
    captured=latest_token(monkeypatch)
    # engineer has no email configured -> same generic response, no mail dispatched
    r=client.post('/api/auth/forgot',json={'username':'engineer'})
    assert r.status_code==200 and 'reset link' in r.json()['notice'].lower()
    assert 'token' not in captured

def test_reset_full_flow(client,monkeypatch):
    captured=latest_token(monkeypatch)
    set_email('engineer','eng@example.test')
    r=client.post('/api/auth/forgot',json={'username':'engineer'})
    assert r.status_code==200
    token=captured['token'];assert captured['to']=='eng@example.test'
    new='Reset-synthetic-pass-2026!'
    r=client.post('/api/auth/reset',json={'token':token,'new_password':new})
    assert r.status_code==200,r.text
    # old password no longer works, new one does
    assert client.post('/api/auth/login',json={'username':'engineer','password':PASSWORD}).status_code==401
    assert client.post('/api/auth/login',json={'username':'engineer','password':new}).status_code==200

def test_reset_token_single_use(client,monkeypatch):
    captured=latest_token(monkeypatch)
    set_email('engineer','eng@example.test')
    client.post('/api/auth/forgot',json={'username':'engineer'})
    token=captured['token']
    assert client.post('/api/auth/reset',json={'token':token,'new_password':'Reset-synthetic-pass-2026!'}).status_code==200
    # reusing the same token must fail
    assert client.post('/api/auth/reset',json={'token':token,'new_password':'Another-synthetic-pass-99!'}).status_code==400

def test_reset_invalid_token(client):
    assert client.post('/api/auth/reset',json={'token':'0000000000badtoken','new_password':'Reset-synthetic-pass-2026!'}).status_code==400

def test_reset_expired_token(client,monkeypatch):
    captured=latest_token(monkeypatch)
    set_email('engineer','eng@example.test')
    client.post('/api/auth/forgot',json={'username':'engineer'})
    token=captured['token']
    with db() as c:c.execute('UPDATE password_resets SET expires=? WHERE used=0',(time.time()-1,))
    assert client.post('/api/auth/reset',json={'token':token,'new_password':'Reset-synthetic-pass-2026!'}).status_code==400

def test_admin_create_user_with_email(client,monkeypatch):
    captured=latest_token(monkeypatch)
    h=auth(client,'admin')
    r=client.post('/api/admin/users',headers=h,json={'username':'mailuser','display_name':'Mail User','role':'Engineer','workspaces':['inhouse'],'email':'mail@example.test'})
    assert r.status_code==200,r.text
    rows=client.get('/api/admin/users',headers=h).json()
    assert any(u['username']=='mailuser' and u['email']=='mail@example.test' for u in rows)
