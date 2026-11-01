"""Targeted tests using synthetic source/database/provider fixtures, not full-app regression."""
import unittest,tempfile,sqlite3,json,sys,os,ast
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlparse
import httpx
from fastapi import HTTPException
import apply_update as update

MAIN='''def save(rt,user,k):
    status='draft' if rt else 'unresolved'
    if True:
        if True:
            if user['id'] in [k['author'],k['editor']]:raise HTTPException(403,'Independent reviewer required, including Administrator-authored entries')
    return status
'''
JS='''const has=()=>true,btn=()=>'',messages=[],files=[];
function detail(){return `${has('knowledge.review')?btn('publish','Publish',true)+btn('archive','Archive')+btn('withdraw','Return to draft'):''}`;}
function reviews(){for(const [id,s] of [['publish','published'],['archive','archived'],['withdraw','draft']]){}}
function bubble(m){return `<button type="button" data-feedback="${m.id}" data-useful="false">Not useful</button></div>`;}
function capture(){on('capture-resolution',async()=>{const first=messages.find(m=>m.role==='user');editing={issue_html:first?.html||$('chat-input').innerHTML,resolution_html:'',environment:''};files=[];page='Add Knowledge';const draft=editing;editing=null;await render();$('issue').innerHTML=draft.issue_html;status('Enter the engineer-validated final resolution. Do not treat an untested AI answer as confirmed.');});}
'''
# Keep a statement in the outer block after removing the independent-review line.
MAIN=MAIN.replace('    return status','            pass\n    return status')
class UpdateTests(unittest.TestCase):
    def fixture(self,root):
        (root/'app/static').mkdir(parents=True);(root/'app/main.py').write_text(MAIN);(root/'app/ai.py').write_text('def call(messages,cfg,json_mode=False):\n    return "old"\n\ndef other():\n    return 1\n');(root/'app/static/app.js').write_text(JS)
    def test_source_transform_and_js_syntax(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);self.fixture(root);original,changes=update.build_changes(root)
            self.assertIn("status='published' if rt",changes['app/main.py']);self.assertNotIn('Independent reviewer required',changes['app/main.py']);self.assertIn('data-correct-answer',changes['app/static/app.js']);self.assertIn("esc(answer.text||'')",changes['app/static/app.js']);self.assertIn("if not is_gemini",changes['app/ai.py']);self.assertEqual((root/'app/main.py').read_text(),MAIN)
    def test_customized_source_refused(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);self.fixture(root);(root/'app/main.py').write_text('pass')
            with self.assertRaises(ValueError):update.build_changes(root)
    def test_new_save_status(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);self.fixture(root);_,changes=update.build_changes(root);ns={};exec(changes['app/main.py'],ns)
            self.assertEqual(ns['save']('resolution',{'id':'a'},{'author':'a','editor':'a'}),'published');self.assertEqual(ns['save']('',{'id':'a'},{'author':'a','editor':'a'}),'unresolved')
    def test_migrate_only_resolved_drafts(self):
        c=sqlite3.connect(':memory:');c.row_factory=sqlite3.Row
        c.executescript('CREATE TABLE knowledge(id TEXT,workspace TEXT,status TEXT,resolution_text TEXT,version INTEGER,updated REAL);CREATE TABLE versions(knowledge_id TEXT,version INTEGER,body TEXT,actor TEXT,note TEXT,created REAL);CREATE TABLE audit(id INTEGER PRIMARY KEY,actor TEXT,action TEXT,target TEXT,workspace TEXT,created REAL,previous TEXT,hash TEXT);')
        for i,s,r in [('a','draft','fix'),('b','unresolved',''),('c','archived','fix'),('d','published','fix')]:c.execute('INSERT INTO knowledge VALUES(?,?,?,?,?,?)',(i,'inhouse',s,r,1,0))
        self.assertEqual(update.migrate(c),1);self.assertEqual(c.execute("SELECT status FROM knowledge WHERE id='a'").fetchone()[0],'published');self.assertEqual(c.execute("SELECT status FROM knowledge WHERE id='c'").fetchone()[0],'archived');self.assertEqual(c.execute('SELECT count(*) FROM versions').fetchone()[0],1);self.assertEqual(c.execute('SELECT count(*) FROM audit').fetchone()[0],1)
    def test_missing_db_refused(self):
        with self.assertRaises(ValueError):update.validate_db(Path('/not-present-synthetic.db'))

    def test_apply_backup_and_migration(self):
        import subprocess
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);self.fixture(root);(root/'.env').write_text('DATABASE_PATH=data/hub-v3.db\n');(root/'data').mkdir();db=root/'data/hub-v3.db'
            with sqlite3.connect(db) as c:
                c.executescript("CREATE TABLE meta(id INTEGER,version INTEGER);INSERT INTO meta VALUES(1,3);CREATE TABLE knowledge(id TEXT,workspace TEXT,status TEXT,resolution_text TEXT,version INTEGER,updated REAL);INSERT INTO knowledge VALUES('a','inhouse','draft','fix',1,0);CREATE TABLE versions(knowledge_id TEXT,version INTEGER,body TEXT,actor TEXT,note TEXT,created REAL);CREATE TABLE audit(id INTEGER PRIMARY KEY,actor TEXT,action TEXT,target TEXT,workspace TEXT,created REAL,previous TEXT,hash TEXT);")
            env=os.environ.copy();env.pop('DATABASE_PATH',None)
            r=subprocess.run([sys.executable,str(Path(update.__file__).resolve()),'--project',str(root),'--apply'],env=env,capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)
            with sqlite3.connect(db) as c:self.assertEqual(c.execute('SELECT status FROM knowledge').fetchone()[0],'published')
            backups=list((root/'upgrade-backups').glob('*/database.db'));self.assertEqual(len(backups),1)
            with sqlite3.connect(backups[0]) as c:self.assertEqual(c.execute('SELECT status FROM knowledge').fetchone()[0],'draft')
            self.assertEqual((root/'.env').read_text(),'DATABASE_PATH=data/hub-v3.db\n')

    def test_answer_prefill_no_automatic_save(self):
        import subprocess,shutil
        if not shutil.which('node'):self.skipTest('Node not installed')
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);self.fixture(root);_,changes=update.build_changes(root)
            helper=changes['app/static/app.js'].split('async function prepareAnswerCorrection',1)[1]
            helper='async function prepareAnswerCorrection'+helper
            harness="""const has=()=>true;let files=[],editing=null,page='Solve Issue';const elements={issue:{},resolution:{}};const $=id=>elements[id];const render=async()=>{};const status=()=>{};const esc=s=>s.replace(/</g,'&lt;');const messages=[{id:'u',role:'user',html:'<p>Original issue</p>',assets:'[\"asset-a\"]'},{id:'a',role:'assistant',text:'Proposed <fix>\\nCheck result'},{id:'u2',role:'user',html:'<p>Follow-up diagnostic</p>',assets:'[]'},{id:'a2',role:'assistant',text:'Corrected candidate'}];"""
            code=harness+helper+"\nprepareAnswerCorrection('a2').then(()=>{if(page!=='Add Knowledge'||files.length!==1||!elements.issue.innerHTML.includes('Follow-up diagnostic')||elements.resolution.innerHTML!=='Corrected candidate')process.exit(1);console.log('PASS');});"
            f=root/'test.js';f.write_text(code);r=subprocess.run(['node',str(f)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)

class ProviderTests(unittest.TestCase):
    def invoke(self,statuses,gemini=True,empty=False,retry_after=None):
        captures=[];statuses=list(statuses)
        class Client:
            def __init__(self,**kw):pass
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def post(self,url,**kw):
                captures.append(kw);code=statuses.pop(0)
                data={'choices':[{'message':{'content':'' if empty else 'Synthetic OK'}}]} if code==200 else {'error':{'code':'synthetic_error','status':'UNAVAILABLE'}}
                return httpx.Response(code,json=data,headers={'retry-after':retry_after} if retry_after else {},request=httpx.Request('POST',url))
        ns={'httpx':httpx,'HTTPException':HTTPException,'urlparse':urlparse,'os':os,'endpoint':lambda c:'https://generativelanguage.googleapis.com/v1beta/openai' if gemini else 'http://localhost:1234/v1'}
        exec((Path(__file__).parent/'provider_call.py.txt').read_text(),ns)
        with patch.object(httpx,'Client',Client),patch('time.sleep'),patch('random.uniform',return_value=0):
            try:return ns['call']([],{'provider':'openai','model':'synthetic'}),captures
            except HTTPException as e:return e,captures
    def test_503_then_success(self):
        result,c=self.invoke([503,200]);self.assertEqual(result,'Synthetic OK');self.assertEqual(len(c),2)
    def test_retry_bounded(self):
        result,c=self.invoke([503,503,503]);self.assertEqual(len(c),3);self.assertEqual(result.detail['upstream_status'],503)
    def test_no_quota_retry(self):
        result,c=self.invoke([429]);self.assertEqual(len(c),1);self.assertEqual(result.detail['upstream_status'],429)
    def test_no_auth_retry(self):
        result,c=self.invoke([403]);self.assertEqual(len(c),1)
    def test_gemini_no_sampling_override(self):
        _,c=self.invoke([200]);self.assertNotIn('temperature',c[0]['json'])
    def test_other_provider_keeps_temperature(self):
        _,c=self.invoke([200],gemini=False);self.assertEqual(c[0]['json']['temperature'],0)
    def test_empty_rejected(self):
        result,c=self.invoke([200],empty=True);self.assertIsInstance(result,HTTPException)
    def test_long_retry_after_not_ignored(self):
        result,c=self.invoke([503],retry_after='120');self.assertEqual(len(c),1);self.assertIsInstance(result,HTTPException)
if __name__=='__main__':unittest.main(verbosity=2)
