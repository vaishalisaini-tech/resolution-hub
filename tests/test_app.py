import json,io,time,uuid
import pytest
from conftest import auth,PASSWORD
B='/api/workspaces/inhouse'
NOTE={'issue_html':'<p>Synthetic parser failure on missing input</p>','resolution_html':'<p>Validate missing values before parsing. Verify with synthetic input.</p>'}
def add(c):
    h=auth(c);r=c.post(B+'/knowledge',headers=h,json=NOTE);assert r.status_code==200,r.text;return r.json()
def publish(c,k):
    h=auth(c,'reviewer');r=c.post('/api/knowledge/'+k['id']+'/review',headers=h,json={'expected_version':k['version'],'status':'published','note':'Synthetic independent review'});assert r.status_code==200,r.text;return r.json()
def test_health(client):assert client.get('/health').json()['version']=='3.0.0'
def test_static(client):
    assert client.get('/').status_code==200
    assert client.get('/static/app.js').status_code==200
    assert 'script-src' in client.get('/').headers['content-security-policy']
def test_no_auth(client):assert client.get('/api/me').status_code==401
def test_login_cookie(client):
    h=auth(client);assert 'rh_session' in client.cookies
    r=client.get('/api/me');assert r.json()['user']['username']=='engineer';assert r.json()['workspaces']==[{'id':'inhouse','name':'Inhouse'}]
def test_bad_password(client):assert client.post('/api/auth/login',json={'username':'engineer','password':'bad'}).status_code==401
def test_csrf(client):
    auth(client);assert client.post(B+'/knowledge',json=NOTE).status_code==403
def test_origin(client):
    assert client.post('/api/auth/login',headers={'Origin':'https://evil.example'},json={'username':'admin','password':PASSWORD}).status_code==403
def test_throttle(client):
    for i in range(10):assert client.post('/api/auth/login',json={'username':'nobody','password':'bad'}).status_code==401
    assert client.post('/api/auth/login',json={'username':'nobody','password':'bad'}).status_code==429
def test_logout(client):
    h=auth(client);assert client.post('/api/auth/logout',headers=h).status_code==200;assert client.get('/api/me').status_code==401
def test_password_change(client):
    h=auth(client);r=client.post('/api/auth/password',headers=h,json={'current_password':PASSWORD,'new_password':'Different-synthetic-pass!'});assert r.status_code==200;assert client.get('/api/me').status_code==401;auth(client,password='Different-synthetic-pass!')
def test_expiry(client):
    auth(client);from app.db import db
    with db() as c:c.execute('UPDATE sessions SET last_seen=0')
    assert client.get('/api/me').status_code==401
def test_workspace_acl(client):
    auth(client);assert client.get('/api/workspaces/rpa/knowledge').status_code==403
def test_reader_write_denied(client):
    h=auth(client,'reader');assert client.post(B+'/knowledge',headers=h,json=NOTE).status_code==403
def test_create_draft(client):
    k=add(client);assert k['status']=='draft';assert k['version']==1
def test_duplicate(client):
    add(client);h=auth(client);assert client.post(B+'/knowledge',headers=h,json=NOTE).status_code==409
def test_unresolved(client):
    h=auth(client);r=client.post(B+'/knowledge',headers=h,json={'issue_html':'Synthetic missing solution'});assert r.json()['status']=='unresolved'
    h=auth(client,'reviewer');assert client.post('/api/knowledge/'+r.json()['id']+'/review',headers=h,json={'expected_version':1,'status':'published','note':'Test review'}).status_code==422
def test_no_self_publish(client):
    h=auth(client,'admin');r=client.post(B+'/knowledge',headers=h,json=NOTE);assert r.status_code==200
    assert client.post('/api/knowledge/'+r.json()['id']+'/review',headers=h,json={'expected_version':1,'status':'published','note':'Self review'}).status_code==403
def test_review_retrieval(client):
    k=publish(client,add(client));h=auth(client);r=client.post(B+'/chat',headers=h,json={'html':'Parser missing input'});assert r.status_code==200,r.text;assert r.json()['sources'][0]['knowledge_id']==k['id']
def test_draft_not_retrieved(client):
    add(client);h=auth(client);assert client.post(B+'/chat',headers=h,json={'html':'Parser missing input'}).json()['sources']==[]
def test_version_conflict(client):
    k=add(client);h=auth(client);r=client.put(B+'/knowledge/'+k['id'],headers=h,json={**NOTE,'expected_version':99});assert r.status_code==409
def test_edit_resets_publication(client):
    k=publish(client,add(client));h=auth(client);r=client.put(B+'/knowledge/'+k['id'],headers=h,json={**NOTE,'expected_version':k['version']});assert r.json()['status']=='draft'
def test_record_scope(client):
    k=add(client);auth(client,'outsider');assert client.get('/api/knowledge/'+k['id']).status_code==403
def test_secret_rejected(client):
    h=auth(client);assert client.post(B+'/knowledge',headers=h,json={**NOTE,'issue_html':'password=notarealsecret'}).status_code==422
def test_html_sanitized(client):
    h=auth(client);r=client.post(B+'/knowledge',headers=h,json={**NOTE,'issue_html':'<script>alert(1)</script><p onclick="bad()">Synthetic issue</p><img src="https://evil/x">'});assert r.status_code==200
    assert 'script' not in r.json()['issue_html'] and 'onclick' not in r.json()['issue_html'] and 'evil' not in r.json()['issue_html']
def test_upload_text_extract_pair(client):
    h=auth(client);r=client.post(B+'/assets',headers=h,files={'file':('case.txt',b'Issue: Synthetic parser missing input\nResolution: Validate input before parsing.','text/plain')});assert r.status_code==200,r.text
    r=client.post(B+'/extract',headers=h,json={'asset_ids':[r.json()['id']]});assert r.status_code==200;assert 'Validate' in r.json()['pairs'][0]['resolution_html']
def test_upload_invalid(client):
    h=auth(client);assert client.post(B+'/assets',headers=h,files={'file':('bad.exe',b'bad')}).status_code==415
def test_upload_invalid_pdf(client):
    h=auth(client);assert client.post(B+'/assets',headers=h,files={'file':('bad.pdf',b'not pdf')}).status_code==422
def test_eml_inline_and_attachment(client):
    from email.message import EmailMessage
    from PIL import Image
    buf=io.BytesIO();Image.new('RGB',(2,2)).save(buf,format='PNG')
    msg=EmailMessage();msg['Subject']='Synthetic email';msg.set_content('Synthetic issue');msg.add_alternative('<p><b>Synthetic issue</b></p><img src="cid:screen">',subtype='html');msg.get_payload()[1].add_related(buf.getvalue(),maintype='image',subtype='png',cid='<screen>',filename='screen.png');msg.add_attachment(b'Issue: Synthetic child\nResolution: Synthetic fix',maintype='text',subtype='plain',filename='case.txt')
    h=auth(client);r=client.post(B+'/assets',headers=h,files={'file':('mail.eml',msg.as_bytes(),'message/rfc822')});assert r.status_code==200,r.text
    a=r.json();assert '<b>Synthetic issue</b>' in a['html'];assert '/api/assets/' in a['html'];assert len(a['children'])==2
    image=next(x for x in a['children'] if x['mime']=='image/png');assert client.get('/api/assets/'+image['id']+'/image').status_code==200
    auth(client,'reader');assert client.get('/api/assets/'+image['id']+'/image').status_code==403
def test_docx(client):
    from docx import Document
    d=Document();d.add_paragraph('Issue: Synthetic DOCX case');d.add_paragraph('Resolution: Synthetic documented fix');buf=io.BytesIO();d.save(buf)
    h=auth(client);r=client.post(B+'/assets',headers=h,files={'file':('case.docx',buf.getvalue())});assert r.status_code==200,r.text;assert 'Synthetic DOCX' in r.json()['text']
def test_import_confirm_required(client):
    h=auth(client);assert client.post(B+'/import',headers=h,json={'pairs':[{**NOTE,'confirmed':False}]}).status_code==422
def test_import_multiple(client):
    h=auth(client);r=client.post(B+'/import',headers=h,json={'pairs':[{**NOTE,'confirmed':True},{'issue_html':'Synthetic second issue','confirmed':True}]});assert r.status_code==200,r.text;assert [k['status'] for k in r.json()['saved']]==['draft','unresolved']
def test_private_history(client):
    h=auth(client);r=client.post(B+'/chat',headers=h,json={'html':'Synthetic test issue'});assert r.status_code==200,r.text;cid=r.json()['conversation_id']
    assert client.post(B+'/chat',headers=h,json={'html':'Follow up question','conversation_id':cid}).status_code==200
    assert len(client.get('/api/conversations/'+cid).json()['messages'])==4
    auth(client,'reader');assert client.get('/api/conversations/'+cid).status_code==404
def test_feedback(client):
    h=auth(client);r=client.post(B+'/chat',headers=h,json={'html':'Synthetic test issue'}).json();assert client.post('/api/messages/'+r['message_id']+'/feedback',headers=h,json={'useful':True}).status_code==200
def test_admin_permissions(client):
    auth(client);assert client.get('/api/admin/users').status_code==403;assert client.get('/api/admin/settings').status_code==403
def test_user_create_forced_change(client):
    h=auth(client,'admin');r=client.post('/api/admin/users',headers=h,json={'username':'newuser','display_name':'New User','role':'Engineer','workspaces':['inhouse']});assert r.status_code==200,r.text
    temp=r.json()['temporary_password'];h=auth(client,'newuser',temp);assert client.get('/api/me').json()['user']['must_change']==1;assert client.get(B+'/knowledge').status_code==403
    assert client.post('/api/auth/password',headers=h,json={'current_password':temp,'new_password':'New-user-synthetic-pass!'}).status_code==200
    auth(client,'newuser','New-user-synthetic-pass!');assert client.get(B+'/knowledge').status_code==200
def test_last_admin_protection(client):
    h=auth(client,'admin');assert client.patch('/api/admin/users/admin',headers=h,json={'role':'Reader','workspaces':['*'],'active':True}).status_code==409
def test_role_create_and_delete(client):
    h=auth(client,'admin');assert client.put('/api/admin/roles',headers=h,json={'name':'Custom','permissions':['solve']}).status_code==200
    assert client.delete('/api/admin/roles/Custom',headers=h).status_code==200
    assert client.put('/api/admin/roles',headers=h,json={'name':'Administrator','permissions':[]}).status_code==403
def test_role_revokes_sessions(client):
    auth(client,'reader');old=client.cookies.get('rh_session');h=auth(client,'admin');assert client.put('/api/admin/roles',headers=h,json={'name':'Reader','permissions':['solve']}).status_code==200
    client.cookies.set('rh_session',old,domain='testserver.local',path='/');assert client.get('/api/me').status_code==401
def test_settings_version(client):
    h=auth(client,'admin');d=client.get('/api/admin/settings').json();body={**d['settings'],'expected_version':d['version']};assert client.put('/api/admin/settings',headers=h,json=body).status_code==200;assert client.put('/api/admin/settings',headers=h,json=body).status_code==409
def test_provider_allowlist(client):
    h=auth(client,'admin');d=client.get('/api/admin/settings').json();assert client.put('/api/admin/settings',headers=h,json={**d['settings'],'expected_version':d['version'],'provider':'openai','base_url':'https://unapproved.example/v1','model':'test'}).status_code==403
def test_scan_fail_closed(client,monkeypatch):
    monkeypatch.setenv('UPLOAD_SCAN','required');monkeypatch.setenv('CLAMSCAN_PATH','/nonexistent/scanner');h=auth(client);assert client.post(B+'/assets',headers=h,files={'file':('case.txt',b'Synthetic test')}).status_code==503
def test_logo(client):
    from PIL import Image
    buf=io.BytesIO();Image.new('RGB',(2,2)).save(buf,format='PNG');h=auth(client,'admin');assert client.post('/api/admin/logo',headers=h,files={'file':('logo.png',buf.getvalue())}).status_code==200;assert client.get('/api/logo').status_code==200
    assert client.delete('/api/admin/logo',headers=h).status_code==200
def test_maintenance(client):
    add(client);h=auth(client,'admin');assert client.post('/api/admin/reindex',headers=h).json()['indexed']==1;assert len(client.get('/api/admin/export').json()['knowledge'])==1;assert client.post('/api/admin/purge-history',headers=h).status_code==200;assert client.get('/api/admin/audit').json()
def test_ai_failure_no_fake_answer(client,monkeypatch):
    import app.ai as ai
    from fastapi import HTTPException
    def fail(*a):raise HTTPException(502,'Synthetic provider failure')
    monkeypatch.setattr(ai,'answer',fail);h=auth(client);assert client.post(B+'/chat',headers=h,json={'html':'Synthetic issue'}).status_code==502;assert client.get(B+'/history').json()==[]

def test_admin_user_reset_revokes(client):
    auth(client,'reader');old=client.cookies.get('rh_session');h=auth(client,'admin');r=client.post('/api/admin/users/reader/reset-password',headers=h);assert r.status_code==200
    client.cookies.set('rh_session',old,domain='testserver.local',path='/');assert client.get('/api/me').status_code==401

def test_asset_cross_workspace_link_denied(client):
    h=auth(client);a=client.post(B+'/assets',headers=h,files={'file':('note.txt',b'Synthetic attachment')}).json()
    h=auth(client,'admin');r=client.post('/api/workspaces/rpa/knowledge',headers=h,json={**NOTE,'asset_ids':[a['id']]});assert r.status_code==403

def test_bulk_import_rollback(client):
    h=auth(client);r=client.post(B+'/import',headers=h,json={'pairs':[{**NOTE,'confirmed':True},{**NOTE,'confirmed':True}]});assert r.status_code==409
    assert client.get(B+'/knowledge').json()==[]

def test_v2_import(client,tmp_path):
    from scripts.import_v2 import import_export
    p=tmp_path/'old.json';p.write_text(json.dumps({'schema_version':2,'instance_id':'lcm','workspace':'inhouse','knowledge':[{'id':'old','workspace':'inhouse','title':'Synthetic old note','content':'Issue: Synthetic parser\nResolution: Validate input'}]}))
    rows=import_export(p,'admin');assert rows and rows[0]['status']=='draft'

def test_login_me_csrf_stable(client):
    h=auth(client);r=client.get('/api/me');assert h['X-CSRF-Token']==r.json()['csrf']

def test_production_guard(client,monkeypatch):
    from app.db import init
    monkeypatch.setenv('APP_ENV','production');monkeypatch.setenv('COOKIE_SECURE','false')
    with pytest.raises(RuntimeError):init()
