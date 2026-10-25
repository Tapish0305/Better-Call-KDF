import json
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest

import api as gateway_api
from accused_lens import api as accused_api
from victim_lens import api as victim_api


TOKEN = 'test-api-token'


def test_vercel_services_bind_gateway_to_private_intake_services():
    config = json.loads((Path(__file__).resolve().parents[1] / 'vercel.json').read_text())

    assert config['services']['app']['root'] == '.'
    assert config['services']['app']['entrypoint'] == 'api:app'
    assert config['services']['accused_lens']['entrypoint'] == 'api:app'
    assert config['services']['victim_lens']['entrypoint'] == 'api:app'
    assert config['services']['app']['bindings'] == [
        {'type': 'service', 'service': 'accused_lens', 'format': 'url', 'env': 'ACCUSED_LENS_URL'},
        {'type': 'service', 'service': 'victim_lens', 'format': 'url', 'env': 'VICTIM_LENS_URL'},
    ]
    assert config['rewrites'] == [
        {'source': '/(.*)', 'destination': {'service': 'app'}}
    ]


def test_gateway_requires_token_except_for_health(monkeypatch):
    monkeypatch.setenv('NYAYA_API_TOKEN', TOKEN)
    client = TestClient(gateway_api.app)

    assert client.get('/health').status_code == 200
    assert client.get('/').status_code == 401
    assert client.get('/', headers={'Authorization': f'Bearer {TOKEN}'}).status_code == 200


def test_gateway_fails_closed_when_token_is_not_configured(monkeypatch):
    monkeypatch.delenv('NYAYA_API_TOKEN', raising=False)
    response = TestClient(gateway_api.app).get('/')

    assert response.status_code == 503
    assert response.json()['detail'] == 'API access is not configured.'


def test_gateway_forwards_to_the_bound_internal_service(monkeypatch):
    monkeypatch.setenv('NYAYA_API_TOKEN', TOKEN)
    monkeypatch.setenv('VICTIM_LENS_URL', 'https://victim.internal/')
    captured = {}

    class FakeResponse:
        is_error = False

        @staticmethod
        def json():
            return {'state': 'created'}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def post(self, url, json, headers):
            captured.update(url=url, json=json, headers=headers)
            return FakeResponse()

    with patch.object(gateway_api.httpx, 'AsyncClient', return_value=FakeClient()):
        response = TestClient(gateway_api.app).post(
            '/api/cases/victim/new',
            headers={'Authorization': f'Bearer {TOKEN}'},
            json={},
        )

    assert response.status_code == 200
    assert response.json() == {'state': 'created'}
    assert captured['url'] == 'https://victim.internal/cases/new'
    assert captured['headers']['Authorization'] == f'Bearer {TOKEN}'


@pytest.mark.parametrize('service_api', [accused_api, victim_api])
def test_internal_service_creates_and_processes_case(monkeypatch, service_api):
    monkeypatch.setenv('NYAYA_API_TOKEN', TOKEN)
    client = TestClient(service_api.app)
    created = client.post('/cases/new', headers={'Authorization': f'Bearer {TOKEN}'})

    assert created.status_code == 200
    state = created.json()
    question = client.post(
        '/cases/next',
        headers={'Authorization': f'Bearer {TOKEN}'},
        json={'state': state},
    ).json()['question']
    assert question['key'] == 'name'

    class FakeExtractor:
        def __init__(self, *args):
            pass

        def extract(self, state, text, asked):
            return service_api.engine.Extraction(updates=[
                service_api.engine.Update(
                    field=asked['key'],
                    value=text,
                    status='answered',
                    quote=text,
                )
            ])

    monkeypatch.setenv('LLM_API_KEY', 'test-key')
    with patch.object(service_api, 'LLMExtractor', FakeExtractor):
        processed = client.post(
            '/cases/process',
            headers={'Authorization': f'Bearer {TOKEN}'},
            json={'state': state, 'text': 'Asha'},
        )

    assert processed.status_code == 200
    assert processed.json()['fields']['name']['value'] == 'Asha'


def test_internal_service_rejects_requests_without_token(monkeypatch):
    monkeypatch.setenv('NYAYA_API_TOKEN', TOKEN)
    response = TestClient(accused_api.app).post('/cases/new')

    assert response.status_code == 401
