# Centralized intake validation

## LiteLLM migration — 25 October 2026

- Active text deployment: `gpt-6-luna` at the configured PenPencil LiteLLM gateway.
- Local credentials are loaded from `.env`; example files contain placeholders.
- Team code is included as request metadata. Access remains controlled by the key.
- 49 central tests, 21 victim tests and 12 accused tests passed (82 total).
- A transport-level test verifies destination URL, bearer authentication, model,
  team metadata, reasoning setting and strict JSON request format.
- Live checks passed for authentication and strict JSON output, then routing,
  extraction and summary generation for synthetic victim and accused accounts.
- This is a compatibility smoke check, not an accuracy benchmark. Sarvam was
  not called during this migration. Earlier validation records below describe
  the original implementation and previous updates.

Base repository: `Tapish0305/Nyaya-Lens-2.0`, commit
`8769f53532868e31d75d2a20744b948f535f17bb`.

## Checks performed

- Python compilation passed for root code and both pipeline packages.
- 25 central tests passed (router schema/evidence validation, ambiguous two-way
  selection, third-party context, opening extraction, pipeline separation,
  restore, atomic rejection, side switching and Streamlit interactions).
- 21 existing victim tests passed.
- 12 existing accused tests passed.
- Total: **58 passing tests**.
- Streamlit AppTest exercised consent/key gating, shared opening questions,
  automatic victim and accused routing, follow-up chat, summary generation,
  summary invalidation on skip, new-case reset, explicit choice after ambiguity,
  extraction failure/retry, routing error recovery, emergency pause/resume and
  switching sides in one interface.
- Both pipelines remain importable simultaneously as distinct packages and
  runnable with their original standalone imports.
- Archive excludes `.env`, `.git`, virtual environments and caches; configuration
  examples contain only placeholders.

## Limits of validation

Router and Groq extraction outputs were mocked in offline tests. No live Groq
request was made and no model classification accuracy measurement is claimed.
Evaluate real victim/accused narratives, mixed-role descriptions, negations,
third-party representation and Hindi/Hinglish on your account before relying on
routing quality. Existing intake and PDF limitations remain as documented.
# Sarvam voice integration validation

Validated using Streamlit 1.65.0 and sarvamai 0.1.37:

- Root suite after multilingual spoken-question update: 46 passed.
- Covered translation before synthesis for Hindi, Bengali, Marathi and Tamil;
  English skips translation. Verified language-specific voice and output codes.
- Streamlit tests cover automatic audio on new questions, no visible question
  text or Listen button, no repeated synthesis/autoplay on draft edits, language
  changes preserving drafts, audio failure/retry, and both intake pipelines.
- Victim engine suite: 21 passed.
- Accused engine suite: 12 passed.
- Checked installed SDK signatures: STT accepts `language_code` and no
  `sample_rate`; streaming TTS accepts `language_code` and yields byte chunks.
- No live Sarvam calls were made. Browser microphone capture, actual playback,
  translation/transcription accuracy and response latency require a valid Sarvam
  key and manual testing in each supported language. Browser policies can block
  autoplay; the audio player's play control remains available.

