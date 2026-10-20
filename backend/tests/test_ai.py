import asyncio
import json
import httpx
import pytest
from app.ai import Ollama, InferenceFailure, cosine, DIMENSIONS
from app.config import settings

def execute(handler,method='extract',text='Монгол Улсын төсөв 400 сая төгрөг.'):
    async def call():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler),base_url='http://ollama') as client:
            return await getattr(Ollama(client),method)(text)
    return asyncio.run(call())

def extraction(**changes):
    data={'summary_quotes':['Монгол Улсын төсөв 400 сая төгрөг.'],'entities':[{'kind':'organization','name':'Монгол Улс','quote':'Монгол Улсын төсөв 400 сая төгрөг.'}],'claims':[{'kind':'money','value':'400 сая төгрөг','quote':'Монгол Улсын төсөв 400 сая төгрөг.'}],'category':'economy','confidence':.7}
    data.update(changes);return httpx.Response(200,json={'message':{'content':json.dumps(data)}})

def test_grounded_schema_and_untrusted_payload():
    def handler(request):
        payload=json.loads(request.content)
        assert payload['format']['type']=='object'
        assert 1<=payload['options']['num_thread']<=8
        assert 'UNTRUSTED' in payload['messages'][0]['content']
        assert json.loads(payload['messages'][1]['content'])['source_text'].startswith('Монгол')
        assert 'tools' not in payload
        return extraction()
    assert execute(handler).claims[0].value=='400 сая төгрөг'

@pytest.mark.parametrize('changes',[{'summary_quotes':['Invented number 999']},{'entities':[{'kind':'organization','name':'Invented','quote':'Монгол Улсын төсөв 400 сая төгрөг.'}]},{'claims':[{'kind':'money','value':'900 сая','quote':'Монгол Улсын төсөв 400 сая төгрөг.'}]}])
def test_hallucinated_evidence_rejected(changes):
    with pytest.raises(InferenceFailure):execute(lambda r:extraction(**changes))

def test_invalid_ai_json():
    with pytest.raises(InferenceFailure):execute(lambda r:httpx.Response(200,json={'message':{'content':'not json'}}))

def test_ollama_timeout_and_retry(monkeypatch):
    monkeypatch.setattr(settings,'ai_retries',1)
    calls=[]
    def fail(request):calls.append(request);raise httpx.ReadTimeout('offline')
    with pytest.raises(InferenceFailure):execute(fail)
    assert len(calls)==2

def test_embedding_validation_and_normalization():
    vector=execute(lambda r:httpx.Response(200,json={'embeddings':[[2.0]+[0.0]*(DIMENSIONS-1)]}),'embed')
    assert vector[0]==1.0 and cosine(vector,vector)==1.0
    for values in [[1.0,0.0],[0.0]*DIMENSIONS,['x']*DIMENSIONS]:
        with pytest.raises(InferenceFailure):execute(lambda r:httpx.Response(200,json={'embeddings':[values]}),'embed')
