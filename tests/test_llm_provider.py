import json

import httpx
from openai import OpenAI
import pytest

import llm_provider
from router import route_query


def test_router_sends_deployment_key_and_team_only_to_configured_proxy(monkeypatch):
    monkeypatch.setenv('LLM_BASE_URL', 'https://proxy.example.test')
    monkeypatch.setenv('LLM_TEAM_CODE', 'team_test')
    captured = []

    def handle(request):
        captured.append(request)
        return httpx.Response(200, json={
            'id': 'test', 'object': 'chat.completion', 'created': 0, 'model': 'gpt-6-luna',
            'choices': [{'index': 0, 'finish_reason': 'stop', 'message': {
                'role': 'assistant', 'content': json.dumps({
                    'route': 'victim', 'needs_clarification': False,
                    'reason': 'Needs help with injuries', 'supporting_quotes': ['I was injured.']})}}],
        })

    transport = httpx.Client(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(llm_provider, 'OpenAI', lambda **kwargs: OpenAI(http_client=transport, **kwargs))
    client = llm_provider.create_client('test-key')
    decision = route_query('I was injured.', 'test-key', client=client)
    assert decision.route == 'victim'
    request = captured[0]
    assert str(request.url) == 'https://proxy.example.test/chat/completions'
    assert request.headers['authorization'] == 'Bearer test-key'
    body = json.loads(request.content)
    assert body['model'] == 'gpt-6-luna'
    assert body['metadata'] == {'team_code': 'team_test'}
    assert body['reasoning_effort'] == 'low'
    assert 'temperature' not in body
    assert body['response_format']['json_schema']['strict'] is True
    assert 'test-key' not in json.dumps(body)
    client.close()


def test_no_team_metadata_when_not_configured(monkeypatch):
    monkeypatch.delenv('LLM_TEAM_CODE', raising=False)
    assert 'extra_body' not in llm_provider.completion_options()


def test_empty_key_rejected_before_connection():
    with pytest.raises(ValueError, match='LLM_API_KEY'):
        llm_provider.create_client(' ')
