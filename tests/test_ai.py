import json,httpx,pytest
from app import ai
from fastapi import HTTPException

def cfg():return {'provider':'openai','base_url':'http://localhost:1234/v1','model':'synthetic-model','vision':False}
def test_evidence_mode():
    result,mode=ai.answer('Synthetic',[],[],[],{'provider':'evidence'});assert mode=='evidence' and 'No matching' in result

def test_chat_contract(monkeypatch):
    captured={}
    class Fake:
        def __init__(self,**kw):pass
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def post(self,url,**kw):
            captured.update(kw);return httpx.Response(200,json={'choices':[{'message':{'content':'Synthetic advisory response'}}]},request=httpx.Request('POST',url))
    monkeypatch.setattr(ai.httpx,'Client',Fake)
    result,mode=ai.answer('Synthetic follow-up',[{'text':'Earlier diagnostic'}],[],[],cfg())
    assert result=='Synthetic advisory response';assert 'Earlier diagnostic' in captured['json']['messages'][1]['content']

def test_vision_contract(monkeypatch):
    captured={}
    def fake(messages,cfg,json_mode=False):captured['messages']=messages;return 'Synthetic image response'
    monkeypatch.setattr(ai,'call',fake);c=cfg();c['vision']=True
    ai.answer('Synthetic image',[],[],[b'synthetic-image-bytes'],c)
    assert captured['messages'][1]['content'][1]['type']=='image_url'

def test_extraction_contract(monkeypatch):
    monkeypatch.setattr(ai,'call',lambda *a:json.dumps({'pairs':[{'issue':'Synthetic issue','resolution':'Documented fix','warnings':[]}]}))
    result=ai.extract_pairs('<p>Synthetic source</p>','source',cfg());assert result[0]['method']=='AI-assisted' and result[0]['confirmed'] is False

def test_unknown_citation_redacted(monkeypatch):
    monkeypatch.setattr(ai,'call',lambda *a:'See 00000000-0000-0000-0000-000000000000:v1')
    result,mode=ai.answer('Synthetic',[],[],[],cfg())
    assert '00000000-0000-0000-0000-000000000000:v1' not in result
    assert '[unverified reference removed]' in result

def test_upstream_quota_safe_error(monkeypatch):
    class Fake:
        def __init__(self,**kw):pass
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def post(self,url,**kw):return httpx.Response(429,json={'error':{'code':'insufficient_quota'}},request=httpx.Request('POST',url))
    monkeypatch.setattr(ai.httpx,'Client',Fake)
    with pytest.raises(HTTPException) as e:ai.call([],cfg())
    assert e.value.detail['upstream_status']==429
