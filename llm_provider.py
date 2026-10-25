"""Shared OpenAI-compatible LiteLLM connection settings."""
import os

from openai import OpenAI

DEFAULT_MODEL = 'gpt-6-luna'
DEFAULT_BASE_URL = 'https://litellm-hackathon.penpencil.guru'


def create_client(api_key):
    if not api_key or not api_key.strip():
        raise ValueError('Set LLM_API_KEY in .env or Connection settings.')
    return OpenAI(
        api_key=api_key.strip(),
        base_url=os.getenv('LLM_BASE_URL', DEFAULT_BASE_URL).rstrip('/') + '/',
        timeout=60.0, max_retries=2,
    )


def completion_options():
    # LiteLLM metadata is for attribution; team access is governed by the API key.
    team = os.getenv('LLM_TEAM_CODE', '').strip()
    return {
        'reasoning_effort': 'low',
        **({'extra_body': {'metadata': {'team_code': team}}} if team else {}),
    }
