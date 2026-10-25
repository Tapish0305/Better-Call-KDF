"""Manual live check using synthetic accounts only; never prints credentials or cases."""
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
from llm_provider import create_client, completion_options, DEFAULT_MODEL
from router import route_query
from intake import get_pipeline, initialize_case


def main():
    load_dotenv(Path(__file__).resolve().parents[1] / '.env')
    key = os.environ['LLM_API_KEY']
    model = os.getenv('LLM_MODEL', DEFAULT_MODEL)
    client = create_client(key).with_options(max_retries=0, timeout=30)
    try:
        response = client.chat.completions.create(
            model=model, messages=[{'role': 'user', 'content': 'Return ok as true.'}],
            **completion_options(), max_completion_tokens=1024,
            response_format={'type': 'json_schema', 'json_schema': {
                'name': 'connection_check', 'strict': True,
                'schema': {'type': 'object', 'properties': {'ok': {'type': 'boolean'}},
                           'required': ['ok'], 'additionalProperties': False}}},
        )
        import json
        assert response.choices[0].finish_reason == 'stop'
        assert json.loads(response.choices[0].message.content)['ok'] is True
        print('PASS: authentication, model access and strict JSON output', flush=True)
        examples = {
            'victim': 'A car hit my bicycle. I hurt my arm and need help with my injuries and losses.',
            'accused': 'Police allege that my car hit a bicycle. I dispute that and need help responding to the allegation.',
        }
        for side, narrative in examples.items():
            decision = route_query(narrative, key, model, name='Test Person',
                                   respondent_role='Myself', client=client)
            assert decision.route == side
            _, extractor_type = get_pipeline(side)
            extractor = extractor_type(key, model)
            extractor.client = client
            state = initialize_case(side, 'Test Person', 'Myself', narrative, extractor, {})
            assert state['fields']['narrative']['value']
            assert extractor.generate_incident_summary(state).strip()
            print(f'PASS: {side} routing, extraction and summary', flush=True)
    except Exception as exc:
        underlying = exc.__context__ or exc
        status = getattr(underlying, 'status_code', None)
        # Error details are sanitized even though the requests contain only synthetic data.
        message = str(underlying).replace(key, '[REDACTED]')[:800]
        print(f'FAIL: {type(underlying).__name__}; HTTP {status}; {message}', flush=True)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
