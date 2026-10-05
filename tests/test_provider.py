import json
from decimal import Decimal
import httpx
import pytest
from campus_assistant.providers.llm import Settings, ProviderError, generate, validate_recommendation, messages_for
GAPS=[{'id':'CPMK-02','gap':23,'evidence_ids':['ASM-02']}]
CONTENT={'activities':[{'cpmk_id':'CPMK-02','evidence_ids':['ASM-02'],'task':'Perbaiki analisis kebutuhan lalu diskusikan hasil dengan dosen.','duration_minutes':30,'assessment_plan':'Nilai kembali berdasarkan rubrik analisis kebutuhan.'}]}

def settings(provider='ollama'):
    return Settings(provider,'test-model','http://127.0.0.1:11434/api/chat','not-a-real-key',Decimal('1000'),Decimal('2000'),800,5000,100000)

def test_schema_grounding_and_no_identifiers():
    validate_recommendation(json.dumps(CONTENT),GAPS)
    bad=json.loads(json.dumps(CONTENT));bad['activities'][0]['evidence_ids']=['OTHER-STUDENT']
    with pytest.raises(ProviderError):validate_recommendation(json.dumps(bad),GAPS)
    bad=json.loads(json.dumps(CONTENT));bad['activities'][0]['duration_minutes']=999
    with pytest.raises(ProviderError):validate_recommendation(json.dumps(bad),GAPS)
    assert 'student_id' not in json.dumps(messages_for(GAPS))

def test_ollama_wire_and_usage():
    def handler(request):
        body=json.loads(request.content)
        assert body['stream'] is False and 'properties' in body['format']
        return httpx.Response(200,json={'done':True,'message':{'content':json.dumps(CONTENT)},'prompt_eval_count':10,'eval_count':20})
    result,inputs,outputs=generate(settings(),messages_for(GAPS),GAPS,httpx.MockTransport(handler))
    assert len(result.activities)==1 and (inputs,outputs)==(10,20)

def test_openai_wire_and_refusal():
    def handler(request):
        body=json.loads(request.content)
        assert body['store'] is False and body['max_completion_tokens']==800
        assert body['response_format']['json_schema']['strict'] is True
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(CONTENT)}}],'usage':{'prompt_tokens':10,'completion_tokens':20}})
    assert generate(settings('openai'),messages_for(GAPS),GAPS,httpx.MockTransport(handler))[1:]==(10,20)
    def refusal(request):return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'refusal':'no'}}]})
    with pytest.raises(ProviderError):generate(settings('openai'),messages_for(GAPS),GAPS,httpx.MockTransport(refusal))

def test_provider_failures_and_config(monkeypatch):
    def handler(request):raise httpx.ReadTimeout('not logged')
    with pytest.raises(ProviderError):generate(settings(),messages_for(GAPS),GAPS,httpx.MockTransport(handler))
    monkeypatch.setenv('AI_PROVIDER','openai');monkeypatch.setenv('AI_MODEL','test-model');monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    with pytest.raises(ProviderError):Settings.load()
    monkeypatch.setenv('AI_PROVIDER','ollama');monkeypatch.setenv('OLLAMA_URL','http://example.com')
    with pytest.raises(ProviderError):Settings.load()
