"""Public Vercel API gateway for routing to the private intake services."""
import hmac
import os
from urllib.parse import urljoin

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from router import route_query

app = FastAPI(title='Nyaya Lens API', version='1.0.0')

SERVICE_BINDINGS = {
    'accused': ('ACCUSED_LENS_URL', 'accused_lens'),
    'victim': ('VICTIM_LENS_URL', 'victim_lens'),
}


class RouteRequest(BaseModel):
    query: str = Field(min_length=1, max_length=12000)
    name: str = Field(default='', max_length=200)
    respondent_role: str = Field(default='', max_length=2000)

    @field_validator('query')
    @classmethod
    def query_must_not_be_blank(cls, value):
        if not value.strip():
            raise ValueError('Incident description must not be blank.')
        return value


@app.middleware('http')
async def require_api_token(request: Request, call_next):
    if request.url.path == '/health':
        return await call_next(request)

    expected = os.getenv('NYAYA_API_TOKEN', '')
    if not expected:
        return JSONResponse(
            status_code=503,
            content={'detail': 'API access is not configured.'},
        )

    authorization = request.headers.get('authorization', '')
    scheme, _, supplied = authorization.partition(' ')
    if scheme.lower() != 'bearer' or not hmac.compare_digest(supplied, expected):
        return JSONResponse(status_code=401, content={'detail': 'Bearer token required.'})
    return await call_next(request)


@app.get('/health')
def health():
    return {'status': 'ok'}


@app.get('/')
def service_info():
    return {
        'service': 'Nyaya Lens API',
        'documentation': '/docs',
        'services': ['accused', 'victim'],
    }


@app.post('/api/route')
def classify_intake(payload: RouteRequest):
    api_key = os.getenv('LLM_API_KEY', '').strip()
    if not api_key:
        raise HTTPException(status_code=503, detail='LLM_API_KEY is not configured.')
    decision = route_query(
        payload.query,
        api_key,
        os.getenv('LLM_MODEL', 'gpt-6-luna'),
        name=payload.name,
        respondent_role=payload.respondent_role,
    )
    return decision.model_dump()


async def call_internal_service(side: str, operation: str, payload: dict, token: str):
    binding, service_name = SERVICE_BINDINGS[side]
    base_url = os.getenv(binding, '').strip()
    if not base_url:
        raise HTTPException(
            status_code=503,
            detail=f'The {service_name} service binding is unavailable.',
        )

    target = urljoin(f'{base_url.rstrip("/")}/', f'cases/{operation.lstrip("/")}')
    try:
        async with httpx.AsyncClient(timeout=70.0) as client:
            response = await client.post(
                target,
                json=payload,
                headers={'Authorization': f'Bearer {token}'},
            )
    except httpx.HTTPError:
        raise HTTPException(
            status_code=502,
            detail=f'The {service_name} service could not be reached.',
        ) from None

    if response.is_error:
        raise HTTPException(
            status_code=response.status_code,
            detail=f'The {service_name} service rejected the request.',
        )
    return response.json()


@app.post('/api/cases/{side}/{operation}')
async def proxy_case_operation(side: str, operation: str, request: Request):
    if side not in SERVICE_BINDINGS:
        raise HTTPException(status_code=404, detail='Unknown intake service.')
    if operation not in {'new', 'process', 'skip', 'next', 'report', 'summary'}:
        raise HTTPException(status_code=404, detail='Unknown case operation.')

    try:
        payload = await request.json()
    except ValueError:
        raise HTTPException(status_code=400, detail='Request body must be valid JSON.') from None
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail='Request body must be a JSON object.')

    authorization = request.headers.get('authorization', '')
    token = authorization.partition(' ')[2]
    return await call_internal_service(side, operation, payload, token)
