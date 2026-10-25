from pathlib import Path
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

from intake import get_pipeline
from router import RouteDecision

APP = str(Path(__file__).resolve().parents[1] / 'app.py')


@pytest.fixture(autouse=True)
def mock_speech():
    # UI tests must never make live/paid calls, including on automatic playback.
    with patch('voice_ui.speak_question', return_value=b'ID3mock-audio') as mock:
        yield mock


def start():
    at = AppTest.from_file(APP, default_timeout=15).run()
    assert not at.exception
    assert at.chat_input[0].disabled
    at.text_input(key='central_llm_api_key').set_value('dummy')
    at.checkbox(key='central_llm_consent').check().run()
    assert not at.chat_input[0].disabled
    at.chat_input[0].set_value('Rahul').run()
    at.chat_input[0].set_value('Myself').run()
    return at


def extractor_class(side, fail=False, emergency=False):
    engine, _ = get_pipeline(side)
    class Fake:
        def __init__(self, *args):
            pass
        def extract(self, state, text, question):
            if fail:
                raise RuntimeError('API unavailable')
            if question['key'] == 'narrative':
                # Verify the controller preserves narrative even if LLM only
                # extracted other facts (or none).
                return engine.Extraction(emergency=emergency,
                    emergency_quote=text if emergency else None)
            return engine.Extraction(updates=[engine.Update(field=question['key'],
                person_id=question['person_id'], value=None, status='unknown', quote=text)])
        def generate_incident_summary(self, state):
            return '# Draft\nUser-reported account.'
    return Fake


def click_label(at, label):
    next(button for button in at.button if button.label == label).click().run()
    assert not at.exception


@pytest.mark.parametrize('side', ['victim', 'accused'])
def test_auto_route_and_continue_in_one_interface(side):
    decision = RouteDecision(route=side, needs_clarification=False,
                              reason='Intake need', supporting_quotes=['incident'])
    with patch('router.route_query', return_value=decision), \
         patch(f'{side}_lens.llm.LLMExtractor', extractor_class(side)):
        at = start()
        at.chat_input[0].set_value('This is my incident.').run()
        assert not at.exception
        case = at.session_state['case']
        assert case['pipeline'] == side
        assert case['fields']['narrative']['value'] == 'This is my incident.'
        assert len(case['messages']) == 3
        at.chat_input[0].set_value("I don't know").run()
        assert not at.exception
        assert len(at.session_state['case']['messages']) == 4
        click_label(at, 'Generate account summary (AI)')
        assert at.session_state['case']['incident_summary']
        click_label(at, 'Skip this question')
        assert at.session_state['case']['incident_summary'] is None
        click_label(at, 'Start a new case')
        assert 'case' not in at.session_state
        assert at.session_state['intake']['stage'] == 'name'


def test_ambiguous_route_explicit_choice():
    decision = RouteDecision(route=None, needs_clarification=True,
                              reason='Need preferred help', supporting_quotes=[])
    with patch('router.route_query', return_value=decision), \
         patch('accused_lens.llm.LLMExtractor', extractor_class('accused')):
        at = start()
        at.chat_input[0].set_value('I was hurt and accused.').run()
        assert not at.exception
        assert 'case' not in at.session_state
        click_label(at, 'Help with allegation against me (accused)')
        assert at.session_state['case']['pipeline'] == 'accused'
        assert at.session_state['case']['routing']['method'] == 'user_choice'


def test_extraction_failure_preserves_opening_for_retry():
    decision = RouteDecision(route='victim', needs_clarification=False,
                              reason='Injury', supporting_quotes=['injured'])
    with patch('router.route_query', return_value=decision), \
         patch('victim_lens.llm.LLMExtractor', extractor_class('victim', fail=True)):
        at = start()
        at.chat_input[0].set_value('I was injured.').run()
        assert not at.exception
        assert 'case' not in at.session_state
        assert at.session_state['intake']['narrative'] == 'I was injured.'
        assert at.error
    with patch('victim_lens.llm.LLMExtractor', extractor_class('victim')):
        click_label(at, 'Continue with selected intake')
        assert at.session_state['case']['pipeline'] == 'victim'


def test_summary_failure_shows_safe_http_status_and_preserves_case():
    decision = RouteDecision(route='victim', needs_clarification=False,
                              reason='Injury', supporting_quotes=['injured'])

    class FailingSummaryExtractor(extractor_class('victim')):
        def generate_incident_summary(self, state):
            error = RuntimeError('private API error details')
            error.status_code = 401
            raise error

    with patch('router.route_query', return_value=decision), \
         patch('victim_lens.llm.LLMExtractor', FailingSummaryExtractor):
        at = start()
        at.chat_input[0].set_value('I was injured.').run()
        click_label(at, 'Generate account summary (AI)')
        assert 'LiteLLM HTTP 401' in at.error[-1].value
        assert 'private API error details' not in at.error[-1].value
        assert at.session_state['case']['incident_summary'] is None
        assert at.session_state['case']['fields']['narrative']['value'] == 'I was injured.'


def test_initial_emergency_pauses_and_resumes():
    decision = RouteDecision(route='victim', needs_clarification=False,
                              reason='Injury', supporting_quotes=['bleeding'])
    with patch('router.route_query', return_value=decision), \
         patch('victim_lens.llm.LLMExtractor', extractor_class('victim', emergency=True)):
        at = start()
        at.chat_input[0].set_value('I am bleeding now.').run()
        assert not at.exception
        assert at.session_state['case']['emergency']
        assert at.chat_input[0].disabled
        click_label(at, 'Everyone is now safe; resume intake')
        assert not at.session_state['case']['emergency']
        assert not at.chat_input[0].disabled


def test_route_failure_never_starts_an_incorrect_case():
    with patch('router.route_query', side_effect=RuntimeError('network')):
        at = start()
        at.chat_input[0].set_value('Please help with the accident.').run()
        assert not at.exception
        assert 'case' not in at.session_state
        assert at.session_state['intake']['stage'] == 'route'
        assert at.error
        assert any(button.label == 'Retry automatic routing' for button in at.button)


def test_switch_sides_without_leaking_fields_between_banks():
    decision = RouteDecision(route='victim', needs_clarification=False,
                              reason='Injury', supporting_quotes=['injured'])
    with patch('router.route_query', return_value=decision), \
         patch('victim_lens.llm.LLMExtractor', extractor_class('victim')), \
         patch('accused_lens.llm.LLMExtractor', extractor_class('accused')):
        at = start()
        at.chat_input[0].set_value('I was injured.').run()
        original_id = at.session_state['case']['id']
        click_label(at, 'Switch to accused intake')
        assert at.session_state['case']['pipeline'] == 'accused'
        assert at.session_state['case']['id'] == original_id
        assert 'allegations' in at.session_state['case']['fields']
        assert len(at.session_state['case']['messages']) == 3


def test_reviewed_voice_answer_uses_existing_opening_flow():
    at = AppTest.from_file(APP, default_timeout=15).run()
    at.text_input(key='central_llm_api_key').set_value('dummy')
    at.text_input(key='central_sarvam_key').set_value('dummy-sarvam')
    at.checkbox(key='central_llm_consent').check()
    at.checkbox(key='central_voice_consent').check().run()
    assert not at.exception
    at.text_area(key='voice_draft').set_value('Rahul').run()
    assert at.session_state['intake']['stage'] == 'name'
    click_label(at, 'Submit reviewed answer')
    assert at.session_state['intake']['name'] == 'Rahul'
    assert at.session_state['intake']['stage'] == 'respondent_role'
    assert at.text_area(key='voice_draft').value == ''


def test_voice_playback_failure_does_not_expose_provider_details(mock_speech):
    mock_speech.side_effect = RuntimeError('private details')
    at = AppTest.from_file(APP, default_timeout=15).run()
    at.text_input(key='central_llm_api_key').set_value('dummy')
    at.text_input(key='central_sarvam_key').set_value('dummy-sarvam')
    at.checkbox(key='central_llm_consent').check()
    at.checkbox(key='central_voice_consent').check().run()
    assert not at.exception
    assert 'private details' not in at.error[-1].value
    assert at.session_state['intake']['stage'] == 'name'
    assert mock_speech.call_count == 1
    at.run()
    assert mock_speech.call_count == 1
    mock_speech.side_effect = None
    click_label(at, 'Retry question audio')
    assert mock_speech.call_count == 2
    assert at.get('audio')[0].proto.autoplay


def enable_voice(at):
    at.text_input(key='central_llm_api_key').set_value('dummy')
    at.text_input(key='central_sarvam_key').set_value('dummy-sarvam')
    at.checkbox(key='central_llm_consent').check()
    at.checkbox(key='central_voice_consent').check().run()
    assert not at.exception
    return at


def test_question_autoplays_once_without_visible_question_or_listen_button(mock_speech):
    at = enable_voice(AppTest.from_file(APP, default_timeout=15).run())
    assert mock_speech.call_count == 1
    assert at.get('audio')[0].proto.autoplay
    assert not any(button.label == 'Listen to question' for button in at.button)
    assert not any('What name would you like' in element.value for element in at.markdown)
    at.text_area(key='voice_draft').set_value('My draft').run()
    assert mock_speech.call_count == 1
    assert not at.get('audio')[0].proto.autoplay
    at.chat_input[0].set_value('Rahul').run()
    assert mock_speech.call_count == 2
    assert at.get('audio')[0].proto.autoplay
    assert all(message.name == 'user' for message in at.chat_message)


@pytest.mark.parametrize('language', ['hi-IN', 'bn-IN', 'mr-IN', 'ta-IN'])
def test_language_switch_speaks_new_language_preserves_draft(mock_speech, language):
    at = enable_voice(AppTest.from_file(APP, default_timeout=15).run())
    at.text_area(key='voice_draft').set_value('Keep this draft').run()
    at.segmented_control(key='conversation_language').set_value(language).run()
    assert not at.exception
    assert mock_speech.call_args.args[2] == language
    assert mock_speech.call_count == 2
    assert at.text_area(key='voice_draft').value == 'Keep this draft'
    assert at.session_state['intake']['stage'] == 'name'
    assert at.get('audio')[0].proto.autoplay


@pytest.mark.parametrize('side', ['victim', 'accused'])
def test_spoken_pipeline_question_and_skip(side, mock_speech):
    decision = RouteDecision(route=side, needs_clarification=False,
                             reason='Intake need', supporting_quotes=['incident'])
    with patch('router.route_query', return_value=decision), \
         patch(f'{side}_lens.llm.LLMExtractor', extractor_class(side)):
        at = enable_voice(AppTest.from_file(APP, default_timeout=15).run())
        at.chat_input[0].set_value('Rahul').run()
        at.chat_input[0].set_value('Myself').run()
        at.chat_input[0].set_value('This is my incident.').run()
        assert not at.exception
        engine, _ = get_pipeline(side)
        expected = engine.next_question(at.session_state['case'])['text']
        assert mock_speech.call_args.args[0] == expected
        assert at.get('audio')[0].proto.autoplay
        assert all(message.name == 'user' for message in at.chat_message)
        before = mock_speech.call_count
        click_label(at, 'Skip this question')
        assert mock_speech.call_count == before + 1
