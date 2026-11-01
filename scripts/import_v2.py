"""Knowledge-only v2 JSON export -> v3 drafts. Never opens/modifies the old database."""
import sys,os,json,argparse
from pathlib import Path
root=Path(__file__).resolve().parents[1];os.chdir(root);sys.path.insert(0,str(root))
from app.db import init,db,config,audit
from app.security import public_user
from app.models import Knowledge
from app.main import save_knowledge
from app.content import plain_html,split_pairs,text

def import_export(path,username):
    payload=json.loads(Path(path).read_text())
    if payload.get('schema_version')!=2 or not isinstance(payload.get('knowledge'),list):raise ValueError('Expected a v2 knowledge export JSON')
    if payload.get('instance_id')!=config()['instance_id']:raise ValueError('Source instance differs; do not copy another team\'s data')
    init();mapped=[]
    with db() as c:
        r=c.execute("SELECT u.*,r.permissions FROM users u JOIN roles r ON r.name=u.role WHERE u.username=? AND u.role='Administrator' AND u.active=1",(username,)).fetchone()
        if not r:raise ValueError('Select an existing active v3 Administrator as import owner')
        user=dict(r);user['workspaces']=json.loads(user['workspaces']);user['permissions']=json.loads(user['permissions'])
        for old in payload['knowledge']:
            workspace=old.get('workspace',payload.get('workspace'))
            raw=plain_html(old.get('title','')+'\n'+old.get('content',''))
            pairs=split_pairs(raw,'v2 export')
            # Heading extraction may find multiple cases; all are drafts/unresolved, never auto-published.
            for p in pairs:
                body=Knowledge(issue_html=p['issue_html'],resolution_html=p['resolution_html'])
                k=save_knowledge(c,workspace,body,user)
                audit(c,user['id'],'v2.import',str(old.get('id',''))+' -> '+k['id'],workspace)
                mapped.append({'old_id':old.get('id'),'new_id':k['id'],'workspace':workspace,'status':k['status']})
    return mapped
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('export_file');p.add_argument('--owner',required=True);a=p.parse_args()
    print(json.dumps(import_export(a.export_file,a.owner),indent=2))
