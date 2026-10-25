"""Optional, session-local voice controls shared by both central intake stages."""
import hashlib

import streamlit as st

from voice import VoiceError, speak_question, transcribe_audio


def clear_voice():
    for key in list(st.session_state):
        if key.startswith('voice_'):
            del st.session_state[key]


def prepare_context(context):
    token = hashlib.sha256(context.encode()).hexdigest()[:20]
    if st.session_state.get('voice_context') != token:
        clear_voice()
        st.session_state.voice_context = token


def spoken_question(context, question, api_key, language, enabled):
    """Generate once per question/language and request autoplay only on first render."""
    if not question or not enabled:
        return
    prepare_context(context)
    identity = hashlib.sha256(f'{context}:{question}:{language}:{api_key}'.encode()).hexdigest()
    if st.session_state.get('voice_audio_identity') != identity:
        st.session_state.voice_audio_identity = identity
        st.session_state.pop('voice_playback', None)
        st.session_state.voice_audio_attempted = False
    if st.session_state.get('voice_audio_attempted') and not st.session_state.get('voice_playback'):
        if st.button('Retry question audio', key='voice_retry'):
            st.session_state.voice_audio_attempted = False
        else:
            st.error('Could not prepare the spoken question. Check your Sarvam key and connection, then retry.')
    fresh = not st.session_state.get('voice_audio_attempted')
    if fresh:
        st.session_state.voice_audio_attempted = True
        try:
            with st.spinner('Preparing your question…'):
                st.session_state.voice_playback = speak_question(question, api_key, language)
        except Exception:
            # Do not expose provider errors, case content or credentials.
            st.rerun()
    if st.session_state.get('voice_playback'):
        with st.container(key='question_player'):
            st.caption('YOUR NEXT QUESTION')
            st.audio(st.session_state.voice_playback, format='audio/mpeg', autoplay=fresh,
                     alt='Spoken intake question in your selected language')
            st.caption('Take your time. Press play to listen again, or if audio hasn’t started.')


def voice_controls(context, api_key, language, enabled):
    """Return only an explicitly reviewed answer; never submit on transcription."""
    if not enabled:
        return None
    prepare_context(context)
    with st.container(key='voice_answer_card'):
        st.markdown('**Over to you.**')
        st.caption('Record your answer here, or type in the chat below. Whatever feels easier.')
        recording = st.audio_input('Record an answer (up to 29 seconds)', sample_rate=16000, key='voice_recording')
        if st.button('Transcribe / append clip', disabled=recording is None, key='voice_transcribe'):
            audio = recording.getvalue()
            digest = hashlib.sha256(audio).hexdigest()
            if digest in st.session_state.get('voice_clips', []):
                st.info('This clip is already in your draft. Record a new clip to add more.')
            else:
                try:
                    with st.spinner('Transcribing your answer…'):
                        text = transcribe_audio(audio, api_key, language)
                    previous = st.session_state.get('voice_draft', '')
                    combined = (previous + '\n' + text).strip()
                    if len(combined) > 12000:
                        raise VoiceError('Your answer exceeds 12,000 characters. Submit this draft before adding more.')
                    st.session_state.voice_draft = combined
                    st.session_state.voice_clips = [*st.session_state.get('voice_clips', []), digest]
                except VoiceError as exc:
                    st.error(str(exc))
                except Exception:
                    st.error('Transcription failed. Your draft is preserved. Check your Sarvam key and connection, then retry.')
        draft = st.text_area('Review and correct your transcript', key='voice_draft', max_chars=12000,
                             help='Check names, dates, vehicle numbers and negations before submitting.')
        if st.button('Submit reviewed answer', disabled=not draft.strip(), key='voice_submit',
                     type='primary', icon=':material/arrow_forward:', width='stretch'):
            return draft.strip()
    return None
