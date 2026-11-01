"""Read saved v3 settings and make ONE synthetic request. Never prints the key."""
import argparse,sys,os,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--project',default='.');a=p.parse_args();root=Path(a.project).resolve();os.chdir(root);sys.path.insert(0,str(root))
from dotenv import load_dotenv
load_dotenv(root/'.env')
from app.db import db,settings
from app.ai import endpoint
import httpx
with db() as c:cfg=settings(c)
print('Saved provider:',cfg['provider']);print('Saved model:',cfg['model'])
print('Key configured:',bool(os.getenv('OPENAI_API_KEY')))
if cfg['provider']=='evidence':raise SystemExit('Evidence-only mode is saved. An earlier 200 test may have made no AI request. Configure Admin > AI Provider.')
base=endpoint(cfg)
if cfg['provider']=='ollama':url=base+'/api/chat';headers={};payload={'model':cfg['model'],'messages':[{'role':'user','content':'Synthetic connectivity test. Reply OK.'}],'stream':False}
else:url=base+'/chat/completions';headers={'Authorization':'Bearer '+os.getenv('OPENAI_API_KEY','')};payload={'model':cfg['model'],'messages':[{'role':'user','content':'Synthetic connectivity test. Reply OK.'}]}
try:
    with httpx.Client(timeout=90,trust_env=False) as c:r=c.post(url,headers=headers,json=payload)
    print('HTTP status:',r.status_code);print('Retry-After:',r.headers.get('retry-after'));print('Request ID:',r.headers.get('x-request-id') or r.headers.get('x-goog-request-id') or 'not supplied')
    if r.is_error:
        try:
            error=r.json().get('error',{});key=os.getenv('OPENAI_API_KEY','')
            for field in ['code','status','message']:
                value=str(error.get(field,''))[:1500]
                if key:value=value.replace(key,'[REDACTED]')
                print(field+':',value)
        except Exception:print('Non-JSON provider error; body not printed.')
    else:print('Synthetic inference request succeeded. No business content was sent.')
except httpx.RequestError as e:print('Transport failure:',type(e).__name__)
