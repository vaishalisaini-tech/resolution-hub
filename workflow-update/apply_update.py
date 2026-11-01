#!/usr/bin/env python3
"""Targeted updater for the supplied Resolution Hub v3.0.0 source.
Dry-run by default. Stop Uvicorn before --apply. Never edits .env or credentials.
"""
import argparse,ast,os,json,sqlite3,time,hashlib,shutil,subprocess,sys,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
MARKER='# Resolution Hub no-approval workflow update 3.0.1'

def once(source,old,new,label):
    if source.count(old)!=1:raise ValueError('Source differs from supported v3.0.0 at '+label+'. No changes applied. Do not force this patch onto customized code.')
    return source.replace(old,new,1)

def build_changes(root):
    paths=['app/main.py','app/ai.py','app/static/app.js']
    originals={name:(root/name).read_text() for name in paths}
    if any(MARKER in v for v in originals.values()):raise ValueError('This update is already applied (or partially applied). Check the backup/manifest before retrying.')
    main=originals['app/main.py']
    main=once(main,"status='draft' if rt else 'unresolved'","status='published' if rt else 'unresolved'",'save state')
    # Remove the second-person approval requirement in the legacy review endpoint too.
    main=once(main,"            if user['id'] in [k['author'],k['editor']]:raise HTTPException(403,'Independent reviewer required, including Administrator-authored entries')\n",'', 'independent review gate')
    main=main.replace("'Unresolved records cannot be published as fixes'","'A resolution is required before making a record searchable'")
    # Keep the archive endpoint for maintenance roles; creation/edit permissions still control saves.
    ai=originals['app/ai.py'];tree=ast.parse(ai)
    node=next((n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='call'),None)
    if node is None:raise ValueError('AI call function not found')
    lines=ai.splitlines(keepends=True);ai=''.join(lines[:node.lineno-1])+(HERE/'provider_call.py.txt').read_text()+'\n'+''.join(lines[node.end_lineno:])
    js=originals['app/static/app.js']
    old="${has('knowledge.review')?btn('publish','Publish',true)+btn('archive','Archive')+btn('withdraw','Return to draft'):''}"
    js=once(js,old,"${has('knowledge.review')?btn('archive','Archive'):''}",'detail approval buttons')
    js=once(js,"for(const [id,s] of [['publish','published'],['archive','archived'],['withdraw','draft']])", "for(const [id,s] of [['archive','archived']])",'detail review actions')
    old="<button type=\"button\" data-feedback=\"${m.id}\" data-useful=\"false\">Not useful</button></div>"
    new="<button type=\"button\" data-feedback=\"${m.id}\" data-useful=\"false\">Not useful</button>${has('knowledge.create')?`<button type=\"button\" data-correct-answer=\"${m.id}\">Edit answer &amp; save as knowledge</button>`:''}</div>"
    js=once(js,old,new,'per-answer correction action')
    old="on('capture-resolution',async()=>{const first=messages.find(m=>m.role==='user');editing={issue_html:first?.html||$('chat-input').innerHTML,resolution_html:'',environment:''};files=[];page='Add Knowledge';const draft=editing;editing=null;await render();$('issue').innerHTML=draft.issue_html;status('Enter the engineer-validated final resolution. Do not treat an untested AI answer as confirmed.');});"
    new="""on('capture-resolution',async()=>{const last=messages.filter(m=>m.role==='assistant').at(-1);if(!last)throw Error('Generate an answer first, or add knowledge manually.');await prepareAnswerCorrection(last.id);});document.querySelectorAll('[data-correct-answer]').forEach(b=>b.onclick=run(async()=>prepareAnswerCorrection(b.dataset.correctAnswer)));"""
    js=once(js,old,new,'existing capture handler')
    js+='''
// Explicit user action only: prefill, allow correction, then use normal RBAC-protected save.
async function prepareAnswerCorrection(messageId){
    if(!has('knowledge.create'))throw Error('Knowledge creation permission required');
    const index=messages.findIndex(m=>m.id===messageId&&m.role==='assistant');
    if(index<0)throw Error('Answer not found in this conversation');
    const answer=messages[index];
    const prior=messages.slice(0,index).filter(m=>m.role==='user');
    const first=prior[0];
    const issueHtml=prior.map((m,i)=>'<h3>'+(i===0?'Original issue':'Follow-up context '+i)+'</h3>'+m.html).join('');
    const ids=[...new Set(prior.flatMap(m=>{try{return JSON.parse(m.assets||'[]');}catch{return [];}}))];
    files=ids.map(id=>({id,name:'Conversation attachment '+id.slice(0,8)}));
    editing=null;page='Add Knowledge';await render();
    $('issue').innerHTML=issueHtml||'<p>No issue context available; enter the issue before saving.</p>';
    $('resolution').innerHTML=esc(answer.text||'').replace(/\\n/g,'<br>');
    status('Review and correct the proposed resolution, then Save knowledge. It becomes searchable immediately. This creates a new record; it does not silently overwrite source knowledge.');
}
'''
    replacements={
      'Save for review':'Save knowledge',
      'Save reviewed cases as drafts':'Save reviewed cases',
      '3 · Save drafts':'3 · Save knowledge',
      'save drafts. No resolution retyping required.':'save knowledge. No resolution retyping required.',
      'Saved. An independent reviewer must publish documented resolutions.':'Saved. Entries with a resolution are searchable immediately; empty resolutions remain unresolved.',
      'Publication is governed by independent review.':'Saved resolutions are searchable immediately. No second-person approval is required.',
      'Publication/review is governed by role permissions.':'Saving is governed by role and workspace permissions.',
      'case(s) saved as drafts/unresolved records.':'case(s) saved as searchable/unresolved records.',
      'Create accounts, assign roles, revoke sessions and manage workspace access.':'Create accounts, assign roles, revoke sessions and manage workspace access.',
      'Needs review':'Unresolved / legacy drafts',
      'Capture final resolution':'Edit answer & save knowledge',
      'drafts, not auto-publication':'knowledge entries',
      'Save creates a draft, or unresolved if resolution is empty.':'Save makes a resolution searchable immediately; an empty resolution stays unresolved.',
      'save drafts. Missing solutions remain unresolved.':'save knowledge. Missing solutions remain unresolved.',
      'as a new draft. AI output is never automatically published.':'as knowledge after explicit user correction and save. AI output is never saved automatically.',
      'Capture the engineer-validated outcome as a new draft.':'Capture the engineer-validated outcome as knowledge.',
      'saved as a draft':'saved as knowledge',
      'Drafts':'Legacy drafts',
      'Published resolutions':'Searchable resolutions'
    }
    for old,new in replacements.items():js=js.replace(old,new)
    # Replace stale guide text that still prescribes independent review.
    js=js.replace('compare against the source and confirm. Missing solutions remain unresolved. AI extraction is optional.','compare against the source and confirm the extraction. Resolutions are searchable on save; missing solutions remain unresolved. AI extraction is optional.')
    changes={'app/main.py':MARKER+'\n'+main,'app/ai.py':MARKER+'\n'+ai,'app/static/app.js':'// '+MARKER[2:]+'\n'+js}
    for name,value in changes.items():
        if name.endswith('.py'):ast.parse(value,filename=name)
    node=shutil.which('node')
    if node:
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'app.js';p.write_text(changes['app/static/app.js']);subprocess.run([node,'--check',str(p)],check=True,capture_output=True)
    return originals,changes

def db_path(root):
    from dotenv import dotenv_values
    cfg=dotenv_values(root/'.env');value=os.getenv('DATABASE_PATH') or cfg.get('DATABASE_PATH') or 'data/hub-v3.db'
    p=Path(value);return p if p.is_absolute() else root/p

def validate_db(path):
    if not path.is_file():raise ValueError('Existing v3 database not found. Refusing to create a new one.')
    c=sqlite3.connect('file:'+str(path.resolve())+'?mode=ro',uri=True)
    try:
        r=c.execute('SELECT version FROM meta WHERE id=1').fetchone()
        if not r or r[0]!=3:raise ValueError('Expected existing schema version 3')
        if c.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('Database integrity check failed')
        n=c.execute("SELECT count(*) FROM knowledge WHERE status='draft' AND length(trim(resolution_text))>0").fetchone()[0]
        return n
    finally:c.close()

def migrate(c):
    rows=c.execute("SELECT * FROM knowledge WHERE status='draft' AND length(trim(resolution_text))>0").fetchall()
    for row in rows:
        k=dict(row);k['status']='published';k['version']+=1;k['updated']=time.time()
        c.execute('UPDATE knowledge SET status=?,version=?,updated=? WHERE id=?',(k['status'],k['version'],k['updated'],k['id']))
        c.execute('INSERT INTO versions(knowledge_id,version,body,actor,note,created) VALUES(?,?,?,?,?,?)',(k['id'],k['version'],json.dumps(k),'workflow-upgrade','Approval removed by instance operator; existing resolved draft made searchable',time.time()))
        prev=c.execute('SELECT hash FROM audit ORDER BY id DESC LIMIT 1').fetchone();prev=prev[0] if prev else '0'*64;t=time.time()
        actor='workflow-upgrade';action='knowledge.approval_removed';target=k['id'];ws=k['workspace']
        digest=hashlib.sha256(json.dumps([actor,action,target,ws,t,prev],separators=(',',':')).encode()).hexdigest()
        c.execute('INSERT INTO audit(actor,action,target,workspace,created,previous,hash) VALUES(?,?,?,?,?,?,?)',(actor,action,target,ws,t,prev,digest))
    return len(rows)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--project',default='.');p.add_argument('--apply',action='store_true');p.add_argument('--keep-existing-drafts',action='store_true',help='Do not make old resolved drafts searchable; new saves still bypass approval');a=p.parse_args()
    root=Path(a.project).resolve();originals,changes=build_changes(root);database=db_path(root);n=validate_db(database)
    print('Validated supported source and existing schema. No .env, account, key or workspace changes.')
    print('Files to update: '+', '.join(changes));print('Existing resolved drafts: '+str(n))
    if not a.apply:
        print('DRY RUN ONLY. Stop the app, then repeat with --apply. Existing resolved drafts become searchable unless --keep-existing-drafts is supplied.');return
    stamp=time.strftime('%Y%m%d_%H%M%S')+'_'+str(os.getpid());backup=root/'upgrade-backups'/stamp;backup.mkdir(parents=True,exist_ok=False);os.chmod(backup,0o700)
    for name in originals:
        dst=backup/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(root/name,dst)
    with sqlite3.connect(database) as src,sqlite3.connect(backup/'database.db') as dst:
        src.backup(dst)
        if dst.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise RuntimeError('Backup verification failed; no application changes applied')
    os.chmod(backup/'database.db',0o600)
    c=sqlite3.connect(database,timeout=20);c.row_factory=sqlite3.Row
    written=[]
    try:
        c.execute('BEGIN IMMEDIATE')
        count=0 if a.keep_existing_drafts else migrate(c)
        for name,value in changes.items():
            path=root/name;tmp=path.with_name(path.name+'.upgrade-tmp');tmp.write_text(value);os.chmod(tmp,path.stat().st_mode & 0o777);tmp.replace(path);written.append(name)
        c.commit()
    except Exception:
        c.rollback()
        for name in written:(root/name).write_text(originals[name])
        raise
    finally:c.close()
    manifest={'update':'3.0.1-no-approval','database':str(database),'migrated_resolved_drafts':count,'files':{n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in changes}}
    (backup/'upgrade.json').write_text(json.dumps(manifest,indent=2))
    print('Applied update. Existing resolved drafts made searchable: '+str(count))
    print('Verified source/database backup: '+str(backup))
    print('Restart Uvicorn, hard-refresh the browser and test. Old test suites that assert mandatory approval must be updated for the new policy.')
if __name__=='__main__':
    try:main()
    except Exception as e:print('UPDATE STOPPED: '+str(e),file=sys.stderr);sys.exit(1)
