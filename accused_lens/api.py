"""Private Vercel API for the accused-side intake engine."""
import hmac
import json
import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

if __package__:
    from . import engine
    from .llm import LLMExtractor
else:
    import engine
    from llm import LLMExtractor

app = FastAPI(title='Nyaya Lens Accused Intake API', version='1.0.0')


class CaseRequest(BaseModel):
    state: dict = Field(default_factory=dict)


class ProcessRequest(CaseRequest):
    text: str = Field(min_length=1, max_length=12000)


@app.middleware('http')
async def require_api_token(request: Request, call_next):
    if request.url.path == '/health':
        return await call_next(request)

    expected = os.getenv('NYAYA_API_TOKEN', '')
    if not expected:
        return JSONResponse(status_code=503, content={'detail': 'API access is not configured.'})
    authorization = request.headers.get('authorization', '')
    scheme, _, supplied = authorization.partition(' ')
    if scheme.lower() != 'bearer' or not hmac.compare_digest(supplied, expected):
        return JSONResponse(status_code=401, content={'detail': 'Bearer token required.'})
    return await call_next(request)


@app.get('/health')
def health():
    return {'status': 'ok'}


def validated_state(payload: CaseRequest):
    if not payload.state:
        raise HTTPException(status_code=422, detail='A case state is required.')
    try:
        return engine.load_case(json.dumps(payload.state))
    except (ValueError, KeyError, TypeError):
        raise HTTPException(status_code=422, detail='The case state is invalid.') from None


def extractor():
    api_key = os.getenv('LLM_API_KEY', '').strip()
    if not api_key:
        raise HTTPException(status_code=503, detail='LLM_API_KEY is not configured.')
    return LLMExtractor(api_key, os.getenv('LLM_MODEL', 'gpt-6-luna'))


@app.post('/cases/new')
def new_case():
    return engine.new_case()


@app.post('/cases/process')
def process_case(payload: ProcessRequest):
    state = validated_state(payload)
    if not payload.text.strip():
        raise HTTPException(status_code=422, detail='Answer text must not be blank.')
    return engine.process(state, payload.text, extractor())


@app.post('/cases/skip')
def skip_case(payload: CaseRequest):
    return engine.skip(validated_state(payload))


@app.post('/cases/next')
def next_case_question(payload: CaseRequest):
    return {'question': engine.next_question(validated_state(payload))}


@app.post('/cases/report')
def case_report(payload: CaseRequest):
    return {'report': engine.report(validated_state(payload))}


@app.post('/cases/summary')
def case_summary(payload: CaseRequest):
    state = validated_state(payload)
    return {'summary': extractor().generate_incident_summary(state)}
