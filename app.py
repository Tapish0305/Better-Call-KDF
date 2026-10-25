"""Central Nyaya Lens app. Run from repository root: python -m streamlit run app.py"""
import hashlib
import json
import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from intake import OPENING_QUESTION, get_pipeline, initialize_case, restore_case, switch_case
from router import CLARIFICATION, route_query
from victim_lens.pdf_export import export_markdown_to_pdf
from voice import LANGUAGES
from voice_ui import clear_voice, spoken_question, voice_controls
from ui_theme import apply_theme, masthead, sidebar_brand, journey, conversation_heading

load_dotenv(Path(__file__).with_name('.env'))
st.set_page_config(page_title='Nyaya Lens · Your story, at your pace', page_icon='⚖️', layout='wide')
apply_theme()
masthead()
speech_language = st.segmented_control(
    'Conversation language', options=list(LANGUAGES), default='en-IN', required=True,
    format_func=lambda code: LANGUAGES[code][0], key='conversation_language', width='stretch',
)


def fresh_intake():
    return {'stage': 'name', 'name': '', 'respondent_role': '', 'narrative': '', 'decision': None}


def reset():
    clear_voice()
    st.session_state.pop('case', None)
    st.session_state.intake = fresh_intake()


if 'intake' not in st.session_state:
    st.session_state.intake = fresh_intake()

with st.sidebar:
    sidebar_brand()
    st.subheader('Before we begin')
    st.caption('Your answers go to LiteLLM to organize your account. Sarvam handles spoken questions and recordings.')
    consent = st.checkbox('I agree to send this intake to LiteLLM.', key='central_llm_consent')
    voice_consent = st.checkbox('Enable voice: send recordings and question text to Sarvam.',
                                key='central_voice_consent')
    with st.expander('Connection settings', icon=':material/settings:'):
        st.caption('Text processing uses the configured LiteLLM hackathon gateway.')
        api_key = st.text_input('LiteLLM API Key', value=os.getenv('LLM_API_KEY', ''),
                                type='password', key='central_llm_api_key').strip()
        model = st.text_input('LiteLLM model ID', value=os.getenv('LLM_MODEL', 'gpt-6-luna'),
                              key='central_llm_model').strip()
        sarvam_key = st.text_input('Sarvam API key', value=os.getenv('SARVAM_API_KEY', ''),
                                   type='password', key='central_sarvam_key').strip()
    ready = consent and bool(api_key) and bool(model)
    if not api_key:
        st.info('Add your API keys in Connection settings to begin.')
    voice_ready = ready and voice_consent and bool(sarvam_key)
    if not voice_ready:
        clear_voice()
    st.divider()
    st.subheader('Your workspace')
    with st.expander('Pick up where you left off', icon=':material/folder_open:'):
        uploaded = st.file_uploader('Resume saved case JSON', type=['json'], key='central_upload')
        if st.button('Load saved case', disabled=uploaded is None, width='stretch'):
            try:
                if uploaded.size > 2_000_000:
                    raise ValueError('File too large')
                restored = restore_case(uploaded.getvalue())
                st.session_state.case = restored
                clear_voice()
                st.rerun()
            except (ValueError, KeyError, TypeError, AttributeError):
                st.error('Invalid saved case. The current session was preserved.')
    if st.button('Start a new case', icon=':material/add:', width='stretch'):
        reset()
        st.rerun()
    st.caption('A little reminder: download your case to save it before leaving. This workspace is temporary.')


def activate(side, method, decision=None):
    intake = st.session_state.intake
    _, extractor_type = get_pipeline(side)
    metadata = {'method': method, 'route': side,
                'decision': decision.model_dump() if decision else intake['decision']}
    with st.spinner('Organizing your description and preparing the next question…'):
        case = initialize_case(side, intake['name'], intake['respondent_role'], intake['narrative'],
                               extractor_type(api_key, model), metadata)
    st.session_state.case = case
    st.rerun()


def classify_and_activate():
    intake = st.session_state.intake
    with st.spinner('Identifying which intake fits your request…'):
        decision = route_query(intake['narrative'], api_key, model,
                               name=intake['name'], respondent_role=intake['respondent_role'])
    intake['decision'] = decision.model_dump()
    if decision.route:
        activate(decision.route, 'llm', decision)
    st.rerun()


def show_error(action, exc=None):
    # Do not render exception bodies, keys or client answers in the UI or logs.
    diagnostic = ''
    if exc is not None:
        status_code = getattr(exc, 'status_code', None)
        diagnostic = f' (LiteLLM HTTP {status_code})' if status_code is not None else f' ({type(exc).__name__})'
    st.error(f'{action} could not complete{diagnostic}. Check your API key, model and connection, then retry. Your current answers are preserved.')


if 'case' not in st.session_state:
    intake = st.session_state.intake
    journey(1)
    conversation_heading(opening=True)
    if not voice_ready:
        st.info('Add your API keys and enable both consent options in the sidebar to hear questions.')
    shared_questions = {
        'name': 'What name would you like me to use?',
        'respondent_role': 'Are you answering for yourself or someone else? If someone else, identify them and your relationship.',
        'narrative': OPENING_QUESTION,
    }
    if any(intake[key] for key in shared_questions):
        with st.expander('Your answers so far', icon=':material/chat_bubble_outline:'):
            for key in shared_questions:
                if intake[key]:
                    with st.chat_message('user'):
                        st.write(intake[key])
    if intake['stage'] in shared_questions:
        spoken_question('opening:' + intake['stage'], shared_questions[intake['stage']],
                        sarvam_key, speech_language, voice_ready)
        voice_answer = voice_controls('opening:' + intake['stage'], sarvam_key, speech_language, voice_ready)
        answer = st.chat_input('Answer naturally…', disabled=not ready, max_chars=12000, key='shared_answer')
        answer = answer or voice_answer
        if answer and answer.strip():
            stage = intake['stage']
            intake[stage] = answer.strip()
            intake['stage'] = {'name': 'respondent_role', 'respondent_role': 'narrative', 'narrative': 'route'}[stage]
            if stage == 'narrative':
                try:
                    classify_and_activate()
                except Exception:
                    show_error('Routing or incident extraction')
            else:
                st.rerun()
    if intake['stage'] == 'route':
        decision = intake['decision']
        if decision and decision['route']:
            st.info(f'The description fits {decision["route"]}-side intake. Continue to organize the incident, or choose the other side below.')
            if st.button('Continue with selected intake', disabled=not ready):
                try:
                    activate(decision['route'], 'llm')
                except Exception:
                    show_error('Incident extraction')
        elif decision:
            spoken_question('opening:route', CLARIFICATION, sarvam_key, speech_language, voice_ready)
        else:
            st.info('Your description is saved in this session. Retry routing or select the help you need below.')
            if st.button('Retry automatic routing', disabled=not ready):
                try:
                    classify_and_activate()
                except Exception:
                    show_error('Routing or incident extraction')
        left, right = st.columns(2)
        with left:
            victim = st.button('Help with injuries / losses (victim)', disabled=not ready, width='stretch')
        with right:
            accused = st.button('Help with allegation against me (accused)', disabled=not ready, width='stretch')
        if victim or accused:
            try:
                activate('victim' if victim else 'accused', 'user_choice')
            except Exception:
                show_error('Incident extraction')
        if st.button('Edit incident description'):
            intake['narrative'] = ''
            intake['decision'] = None
            intake['stage'] = 'narrative'
            st.rerun()
    st.stop()

state = st.session_state.case
side = state['pipeline']
engine, extractor_type = get_pipeline(side)
journey(3 if state['reviewed'] else 2)

with st.sidebar:
    st.divider()
    st.subheader('Intake side')
    st.caption('If the selected side does not fit, switch it. Existing answers will be reprocessed for that intake.')
    other = 'accused' if side == 'victim' else 'victim'
    if st.button(f'Switch to {other} intake', disabled=not ready or state['emergency']):
        try:
            with st.spinner('Reorganizing your answers for the selected intake…'):
                switched = switch_case(state, other, get_pipeline(other)[1](api_key, model))
            st.session_state.case = switched
            clear_voice()
            st.rerun()
        except Exception:
            show_error('Switching intake')
    st.divider()
    st.subheader('Reports and exports')
    brief = engine.report(state)
    st.download_button('Save case JSON', json.dumps(state, ensure_ascii=False, indent=2),
                       f'nyaya-{side}-{state["id"]}.json', 'application/json')
    st.download_button('Download lawyer brief (MD)', brief, f'nyaya-{side}-brief.md', 'text/markdown')
    st.download_button('Download lawyer brief (PDF)', export_markdown_to_pdf(
        f'Nyaya Lens — {side.capitalize()}-side intake brief', f'Case ID: {state["id"]}', brief),
        f'nyaya-{side}-brief.pdf', 'application/pdf')
    if st.button('Generate account summary (AI)', disabled=not ready or state['emergency']):
        try:
            with st.spinner('Preparing the account summary…'):
                summary = extractor_type(api_key, model).generate_incident_summary(state)
            state['incident_summary'] = summary
            state['reviewed'] = False
            st.rerun()
        except Exception as exc:
            show_error('Summary generation', exc)
    if state.get('incident_summary'):
        st.download_button('Download account summary (MD)', state['incident_summary'],
                           f'nyaya-{side}-summary.md', 'text/markdown')
        st.download_button('Download account summary (PDF)', export_markdown_to_pdf(
            f'{side.capitalize()}-side account summary', f'Case ID: {state["id"]}', state['incident_summary']),
            f'nyaya-{side}-summary.pdf', 'application/pdf')

chat, details = st.columns([1.65, 1], gap='large')
with details:
    st.subheader('Your case file', anchor=False)
    st.caption(f'{side.capitalize()} intake · Ready to review as you go')
    if state.get('incident_summary'):
        with st.expander('Account summary', expanded=True):
            st.markdown(state['incident_summary'])
    with st.expander('Lawyer brief', icon=':material/description:'):
        st.text(engine.report(state))
    with st.expander('Case facts and sources'):
        st.json(state)
    fingerprint = hashlib.sha256((engine.report({**state, 'reviewed': False}) + str(state.get('incident_summary'))).encode()).hexdigest()[:16]
    reviewed = st.checkbox('I reviewed the summary and confirm it reflects my account.',
                           value=state['reviewed'], key=f'central_review_{state["id"]}_{side}_{fingerprint}')
    if reviewed != state['reviewed']:
        state['reviewed'] = reviewed
        st.rerun()

with chat:
    conversation_heading()
    with st.expander(f'Your answers so far · {len(state["messages"])}', icon=':material/chat_bubble_outline:'):
        for message in state['messages']:
            with st.chat_message('user'):
                st.write(message['text'])
    question_context = f'{state["id"]}:{side}:{len(state["messages"])}'
    if not voice_ready:
        st.info('Add your API keys and enable both consent options in the sidebar to hear questions.')
    if state['emergency']:
        st.error('Your account indicates a current unresolved emergency. Pause the intake and seek immediate local emergency assistance.')
        if st.button('Everyone is now safe; resume intake'):
            state['emergency'] = False
            state['reviewed'] = False
            state['incident_summary'] = None
            state['messages'].append({'id': f'm{len(state["messages"])+1}', 'role': 'user',
                                      'text': '[User confirmed current safety]', 'question': None})
            st.rerun()
    else:
        question = engine.next_question(state)
        if question:
            spoken_question(question_context, question['text'], sarvam_key, speech_language, voice_ready)
            if st.button('Skip this question', disabled=not consent):
                st.session_state.case = engine.skip(state)
                st.rerun()
        else:
            st.success('The intake is complete or remaining details need lawyer follow-up. Review your brief; you can still add or correct facts below.')
    voice_answer = voice_controls(question_context, sarvam_key, speech_language,
                                  voice_ready and not state['emergency'])
    answer = st.chat_input('Answer naturally, add details, or correct an earlier answer…',
                           disabled=not ready or state['emergency'], max_chars=12000, key='pipeline_answer')
    answer = answer or voice_answer
    if answer and answer.strip():
        try:
            with st.spinner('Organizing the facts from your answer…'):
                updated = engine.process(state, answer, extractor_type(api_key, model))
            st.session_state.case = updated
            st.rerun()
        except Exception:
            show_error('Fact extraction')
