"""Optional Playwright browser regression. Uses a temporary DB and synthetic records."""
import os,sys,tempfile,subprocess,time,json,socket
from pathlib import Path
import httpx
from playwright.sync_api import sync_playwright,expect
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
with tempfile.TemporaryDirectory() as td:
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    env=os.environ.copy();env.update(DATABASE_PATH=str(Path(td)/'browser.db'),INSTANCE_CONFIG=str(root/'config/instance.json'),APP_ENV='development',COOKIE_SECURE='false',CHAT_PROVIDER='evidence',UPLOAD_SCAN='off',OCR_ENABLED='false',ALLOWED_ORIGINS=f'http://127.0.0.1:{port}')
    seed="""from app.db import init,db
from app.security import hash_password
import time,json
init()
with db() as c:
 for name,role in [('admin','Administrator'),('engineer','Engineer'),('reviewer','Reviewer')]:
  c.execute('INSERT INTO users VALUES(?,?,?,?,?,?,?,?,?)',(name,name,name,hash_password('Synthetic-browser-pass!'),role,'[\"*\"]',1,0,time.time()))
"""
    subprocess.run([sys.executable,'-c',seed],cwd=root,env=env,check=True)
    log=open(Path(td)/'server.log','w');proc=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(port)],cwd=root,env=env,stdout=log,stderr=log)
    try:
        url=f'http://127.0.0.1:{port}'
        for _ in range(100):
            try:
                if httpx.get(url+'/health',timeout=1).status_code==200:break
            except Exception:pass
            time.sleep(.1)
        else:raise RuntimeError('Server did not start')
        with sync_playwright() as p:
            opts={'executable_path':os.environ['CHROMIUM_EXECUTABLE']} if os.getenv('CHROMIUM_EXECUTABLE') else {}
            browser=p.chromium.launch(headless=True,args=['--no-sandbox'],**opts);page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            def login(name):
                page.goto(url);page.locator('#username').fill(name);page.locator('#password').fill('Synthetic-browser-pass!');page.get_by_role('button',name='Sign in',exact=True).click();page.get_by_role('heading',name='Knowledge into action').wait_for()
            def nav(name):page.locator('#nav').get_by_role('button',name=name,exact=True).click()
            login('engineer');assert page.locator('#workspace option').all_text_contents()==['Inhouse','Enable','RPA','MATE']
            nav('Add Knowledge');page.locator('#file-input').set_input_files({'name':'synthetic-cases.txt','mimeType':'text/plain','buffer':b'Issue: Synthetic parser failure on missing input\nResolution: Validate missing values before parsing. Verify with synthetic input.'})
            page.get_by_text('File extracted. Review the content before saving or sending.',exact=True).wait_for()
            page.locator('#extract').click();page.get_by_role('heading',name='Both fields, extracted together.').wait_for();assert 'Validate missing values' in page.locator('#pair-resolution').inner_text();page.locator('#pair-confirm').check();page.locator('#import-save').click();page.get_by_role('heading',name='Knowledge library',exact=True).wait_for()
            page.locator('#logout').click();login('reviewer');nav('Library');page.get_by_role('button',name='Open',exact=True).click();page.once('dialog',lambda d:d.accept('Synthetic independent browser review'));page.locator('#publish').click();page.get_by_text('Review saved.',exact=True).wait_for();assert page.locator('.badge.green').inner_text()=='published'
            page.locator('#logout').click();login('engineer');nav('Solve Issue');page.locator('#chat-input').fill('Synthetic parser missing input');page.locator('#send').click();page.get_by_text('Evidence-only mode. No AI model was called.',exact=False).first.wait_for();assert 'Validate missing values' in page.locator('.bubble').last.inner_text();page.locator('#chat-input').fill('What should I validate next?');page.locator('#send').click();expect(page.locator('.bubble')).to_have_count(4)
            nav('History');page.get_by_role('button',name='Resume',exact=True).click();expect(page.locator('.bubble')).to_have_count(4)
            page.locator('#workspace').select_option('rpa');page.locator('#chat-input').fill('Synthetic parser missing input');page.locator('#send').click();page.get_by_text('No matching published resolution found.',exact=False).wait_for()
            page.locator('#logout').click();login('admin');nav('Users');page.locator('#new-username').fill('browser.user');page.locator('#new-display').fill('Browser User');page.locator('#add-user').click();page.locator('#modal').wait_for(state='visible');assert 'Temporary password' in page.locator('#modal').inner_text();page.locator('#modal-close').click()
            nav('Admin');page.get_by_role('button',name='Roles & RBAC',exact=True).click();page.locator('#role-name').fill('Browser Role');page.locator('#create-role').click();page.get_by_text('Role created.',exact=True).wait_for()
            for tab in ['Workspaces','AI Provider','Branding','Security','Imports','Audit','Backup & Retention']:
                page.get_by_role('button',name=tab,exact=True).click();page.wait_for_timeout(120)
            nav('Guide');page.get_by_role('heading',name='A simpler knowledge workflow').wait_for();page.locator('#profile').click();page.get_by_role('heading',name='Profile & preferences').wait_for()
            nav('Dashboard');page.get_by_role('heading',name='Knowledge into action').wait_for()
            if os.getenv('SCREENSHOT_DIR'):
                dest=Path(os.environ['SCREENSHOT_DIR']);dest.mkdir(parents=True,exist_ok=True);page.screenshot(path=str(dest/'dashboard-dark.png'),full_page=True);page.locator('#theme').click();page.screenshot(path=str(dest/'dashboard-light.png'),full_page=True)
            page.set_viewport_size({'width':375,'height':900});assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
            assert not errors,errors;browser.close()
        print('PASS: real login, four workspaces, complete-file import, prefilled resolution, independent review, evidence retrieval, continuing chat, history, workspace isolation, users, roles, admin pages, themes, responsive layout; no browser page errors.')
    except Exception:
        print(Path(td,'server.log').read_text()[-5000:]);raise
    finally:
        proc.terminate()
        try:proc.wait(timeout=10)
        except subprocess.TimeoutExpired:proc.kill();proc.wait()
        log.close()
