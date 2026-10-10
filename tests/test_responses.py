import json

import httpx
import pytest

from agents.responses import ResponsesBackend, ChatBackend
from agents.docker import PrerequisiteError
from controller.config import ExperimentConfig


@pytest.mark.parametrize('mode', ['ok', 'malformed', 'auth'])
@pytest.mark.parametrize('backend_class', [ResponsesBackend, ChatBackend])
def test_responses_has_only_current_source_and_explicit_input(tmp_path, monkeypatch, mode, backend_class):
    root=tmp_path/'workspace'
    (root/'app').mkdir(parents=True)
    (root/'contracts').mkdir()
    (root/'app/main.py').write_text('CURRENT SOURCE')
    (tmp_path/'private.txt').write_text('RESEARCHER SENTINEL')
    (root/'history.txt').write_text('HIDDEN HISTORY')
    monkeypatch.setenv('SOCLAAS_API_KEY','private-credential')
    calls=[]
    def handler(request):
        body=json.loads(request.content)
        calls.append(body)
        field='messages' if backend_class==ChatBackend else 'input'
        assert 'CURRENT SOURCE' in body[field][0]['content']
        if backend_class==ChatBackend:
            assert body['tool_choice']=='none'
            assert body['response_format']['json_schema']['strict'] is True
            assert 'interpretation' in body['response_format']['json_schema']['schema']['required']
            assert request.url.path == '/v1/chat/completions'
        assert 'RESEARCHER SENTINEL' not in request.content.decode()
        assert 'HIDDEN HISTORY' not in request.content.decode()
        assert 'private-credential' not in request.content.decode()
        assert 'previous_response_id' not in body and 'tools' not in body
        if mode=='auth':
            return httpx.Response(401,json={'error':'invalid credential'})
        answer=json.dumps({'schema_version':1,'interpretation':'Measured outcome','limitations':[]}) if mode=='ok' else '```json\n{}\n```'
        if backend_class==ChatBackend:
            return httpx.Response(200,json={'model':'reported-model','choices':[{'message':{'content':answer},'finish_reason':'stop'}],'usage':{'prompt_tokens':50,'completion_tokens':20}})
        return httpx.Response(200,json={'model':'default','output_text':answer,'usage':{'input_tokens':50,'output_tokens':20}})
    client=httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr('agents.responses.httpx.Client',lambda **kwargs:client)
    cfg=ExperimentConfig(epsilon=.2,benchmark={},model='default',provider_base_url='https://example.edu/v1',provider_key_env='SOCLAAS_API_KEY',max_tool_calls=0)
    backend=backend_class(cfg)
    if mode=='auth':
        with pytest.raises(PrerequisiteError,match='401'):
            backend.invoke('auditor',{},root,tmp_path/'artifacts')
    else:
        result=backend.invoke('auditor',{},root,tmp_path/'artifacts')
        assert result.status==('ok' if mode=='ok' else 'malformed')
        assert result.usage['input_tokens']==50 and result.usage['output_tokens']==20
    assert len(calls)==1
    assert all('private-credential' not in p.read_text() for p in (tmp_path/'artifacts').iterdir())
