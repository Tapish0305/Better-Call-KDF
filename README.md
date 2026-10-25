# Better-Call-KDF

Nyaya Lens — multilingual voice intake for road accident accounts.

One Streamlit app asks shared opening questions, uses LiteLLM to choose **victim** or
**accused** intake, then continues with that side's existing question bank.
Routing selects the person's intake need; it does not determine legal fault.

## Run on Windows

Open a terminal in the extracted project folder (the folder containing this README
and the root `app.py`), then:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Set `LLM_API_KEY` in `.env`, or enter your key in the app sidebar. Keep `.env`
local. The default model is `gpt-6-luna`; choose a model supporting strict
JSON-schema responses and available to your LiteLLM account. Tick the consent box.
No real API key is included in this package.

The text backend uses the OpenAI-compatible LiteLLM gateway. Local configuration:

```env
LLM_API_KEY=your_litellm_key
LLM_BASE_URL=https://litellm-hackathon.penpencil.guru
LLM_MODEL=gpt-6-luna
LLM_TEAM_CODE=team_141
```

Keep actual keys only in `.env` or the password field. `LLM_TEAM_CODE` is sent as
LiteLLM request metadata; the gateway assigns permissions through the API key.
Routing, both extraction pipelines and optional summaries use this deployment.
Requests use low reasoning effort, omit temperature, and retain strict JSON
schemas and local validation. Sarvam continues handling speech and translation.
Restart the running app after changing environment configuration.

For an optional **live API check** using synthetic cases (consumes API tokens):

```powershell
.\.venv\Scripts\python.exe scripts/check_llm.py
```

On macOS/Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
# Edit .env with your key
.venv/bin/python -m streamlit run app.py
```

Use the **root app.py** for centralized intake. Both standalone apps remain
runnable from their own folders using their original instructions.

## Vercel services deployment

`vercel.json` defines three Python services. Vercel's public `/` route targets
the `app` API gateway; `accused_lens` and `victim_lens` remain internal and are
called by the gateway through service bindings. The ASGI APIs are in `api.py`
at each service root. Existing Streamlit entrypoints remain available for local
development, but Vercel deploys the JSON APIs rather than the Streamlit UI.

Configure these Vercel environment variables for all three services:

- `NYAYA_API_TOKEN`: a long, random bearer token required by the gateway and
  internal APIs.
- `LLM_API_KEY`: the LiteLLM key. `LLM_BASE_URL`, `LLM_MODEL`, and
  `LLM_TEAM_CODE` are optional overrides.

Vercel injects `ACCUSED_LENS_URL` and `VICTIM_LENS_URL` into the `app` service
from its bindings. Do not create or populate these variables manually.
Requests to the gateway use `Authorization: Bearer <NYAYA_API_TOKEN>`.
The case endpoints are `POST /api/cases/{victim|accused}/{new|process|skip|next|report|summary}`;
`POST /api/route` classifies the opening description. Case state is sent by the
client on each request and is not persisted by these APIs. Treat case JSON and
API tokens as sensitive, and configure production access controls before
handling real client information.

## How it works

### Multilingual spoken questions

Choose **Hindi, English, Bengali, Marathi or Tamil** at the top of the central
app. Questions are spoken automatically in that language, without displaying
question text in the conversation or requiring a Listen button. Sarvam Translate
translates English questions before Bulbul v4 Flash generates speech. GPT-6 Luna through
LiteLLM performs routing and fact extraction; Python chooses the next question.

Install the root requirements, set `SARVAM_API_KEY` in your local `.env` (or enter
it in the sidebar), and enable both LiteLLM and Sarvam consent. Questions require
Sarvam to be configured. If your browser blocks automatic audio, use the player's
play control; it also lets you replay the question. Audio is generated once for
the current question and language, and ordinary UI updates do not regenerate it
or request autoplay again. Changing the language speaks the current question in
the new language and preserves your unsubmitted voice draft. Translation/audio
failures show an explicit retry control without falling back to spoken English.

Record clips up to 29 seconds, click **Transcribe / append clip**, review the
editable draft, then click **Submit reviewed answer**. Longer narratives can be
assembled from multiple clips. Transcription alone never submits case facts.
Saaras v4 uses the selected conversation language for transcription. Typed
answers remain available. A failed transcription preserves the draft; a
failed extraction preserves it for retry. Source quotes refer to the submitted,
user-reviewed text, not verified words from the audio recording.

Audio and drafts stay in temporary session/widget memory and are not included in
case exports or written to audio files. Sarvam receives audio for transcription
and question text for translation/speech generation; LiteLLM receives submitted text for intake.
Provider retention policies apply separately. New cases and loaded/switched cases
clear voice drafts. The standalone apps remain text-only.

Offline tests cover speech request construction and intake integration. Live
Sarvam accuracy, latency, browser microphone permission and audio playback still
need checking with a valid key and representative recordings in all five languages.
The conversation's questions are localized; report content and general interface
controls are not automatically translated. Source question text stays in case
metadata for review and exports.

1. Ask the name to use.
2. Ask whether the speaker represents themselves or someone else, and whom.
3. Ask for the whole incident and the help requested.
4. `route_query()` in `router.py` classifies the account using LiteLLM and strict JSON.
5. If the account does not clearly select a side, the same UI offers two buttons:
   help with injuries/losses (**victim**) or help with an allegation against the
   represented person (**accused**). There is no third pipeline.
6. Seed the name and representation answers with source messages; extract the
   opening incident directly into the selected bank. Keep the raw opening account
   as narrative if the extractor omitted that field.
7. Python selects the next applicable unanswered question, skipping fields already
   supplied in the opening account.

Victim intake collects per-person injury/treatment/financial information. Accused
intake distinguishes allegations from the represented client's account and asks
about police contact, notices, disputed evidence and proceedings.

The router receives the opening account and representation answers. It requires
verbatim supporting quotes, validates its decision, and attempts up to three
responses if output validation fails. Invalid output or API errors do not silently
choose a side. Quotes and schemas do not prove the semantic classification is
correct; the user can override the route.

## Router function

```python
from router import route_query

decision = route_query(
    "Police allege that my car hit a bike. I dispute this and need help responding.",
    api_key="your-local-key",
    name="Rahul",
    respondent_role="I am answering for myself",
)

if decision.needs_clarification:
    # Ask the user to choose victim or accused.
    pass
else:
    print(decision.route)  # 'victim' or 'accused'
```

A `null` route is a request for clarification, not a third intake type. Responses
include `route`, `needs_clarification`, `reason`, and `supporting_quotes`.

## Case controls

- Continue either intake in the same chat interface.
- Skip questions, correct facts, inspect state and review source-linked briefs.
- Export JSON, Markdown and PDF; generate an optional AI account summary.
- Restore a saved case into its own pipeline. Legacy victim JSON exports without
  a `pipeline` key are supported.
- Switch sides through the sidebar. All original user answers are re-extracted
  into the new bank rather than copying incompatible fields. This makes one
  extraction call per original answer and can take time on long cases. A failed
  switch preserves the previous case; switching clears generated summaries and
  review confirmation.
- Pause for an emergency flagged by extraction and resume after a safety
  confirmation. This is not reliable emergency triage.

The central app stores routing metadata alongside `pipeline` in case JSON. API
keys are never stored in that state. Router decisions are not rerun for every
answer; the user can switch the intake if their help request changes.

## Files and integration

| File | Role |
|---|---|
| `app.py` | Central Streamlit interface |
| `router.py` | LLM routing function and validated two-way decision schema |
| `intake.py` | Pipeline dispatch, shared-answer seeding, restore and side switching |
| `victim_lens/` | Victim bank, state engine, extractor and exports |
| `accused_lens/` | Accused bank, state engine, extractor and exports |
| `tests/` | Router, integration and Streamlit interaction tests |

Both packages now support relative imports when used centrally and original
imports when launched standalone. Victim-side new answers/skips also clear stale
AI summaries, and plaintext answer logging was removed. Configuration examples
contain placeholders.

To integrate into an existing clone, copy the root files and updated pipeline
folders from this package. Preserve your own local `.env`. This package is based
on repository commit `8769f53532868e31d75d2a20744b948f535f17bb`.

## Tests

Run these from the root folder:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest -q -c victim_lens/pytest.ini victim_lens/tests
.\.venv\Scripts\python.exe -m pytest -q -c accused_lens/pytest.ini accused_lens/tests
```

Alternatively run each pipeline's tests from its own folder, as documented in its
README. See `VALIDATION.md` for checks actually performed.

## Prototype limits

No login, database, document OCR or legal research is added. Cases remain in
Streamlit session memory until you download JSON. Exports contain the submitted
case details. PDF export uses the existing ReportLab exporter and its fonts have
limited Hindi coverage. Live LiteLLM smoke checks passed with synthetic victim and accused accounts;
classification quality on real narratives and Hindi/Hinglish needs evaluation
with your own account. The existing field validators and summary prompts are
retained apart from the integration changes described above.
