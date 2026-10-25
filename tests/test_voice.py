import io
import wave
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from voice import LANGUAGES, VoiceError, speak_question, transcribe_audio


def wav(seconds=1):
    out = io.BytesIO()
    with wave.open(out, 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b'\0\0' * (16000 * seconds))
    return out.getvalue()


def test_transcript_keeps_language_and_negation():
    client = Mock()
    client.speech_to_text.transcribe.return_value = SimpleNamespace(transcript='  मैंने टक्कर नहीं मारी।  ')
    assert transcribe_audio(wav(), 'secret', 'hi-IN', client=client) == 'मैंने टक्कर नहीं मारी।'
    request = client.speech_to_text.transcribe.call_args.kwargs
    assert request['mode'] == 'transcribe'
    assert request['language_code'] == 'hi-IN'
    assert request['model'] == 'saaras:v4'


@pytest.mark.parametrize('audio', [b'invalid', wav(30), wav(0)], ids=['invalid', 'too-long', 'empty'])
def test_invalid_or_long_audio_never_sent(audio):
    client = Mock()
    with pytest.raises(VoiceError):
        transcribe_audio(audio, 'secret', client=client)
    client.speech_to_text.transcribe.assert_not_called()


def test_silence_requires_retry():
    client = Mock()
    client.speech_to_text.transcribe.return_value = SimpleNamespace(transcript=' ')
    with pytest.raises(VoiceError, match='No speech'):
        transcribe_audio(wav(), 'secret', client=client)


def test_tts_collects_stream_and_sets_matching_codec():
    client = Mock()
    client.text_to_speech.convert_stream.return_value = iter([b'first', b'second'])
    assert speak_question('What happened?', 'secret', client=client) == b'firstsecond'
    request = client.text_to_speech.convert_stream.call_args.kwargs
    assert request['output_audio_codec'] == 'mp3'
    assert request['language_code'] == 'en-IN'
    assert request['model'] == 'bulbul:v4-flash'
    client.text.translate.assert_not_called()


@pytest.mark.parametrize('language', ['hi-IN', 'bn-IN', 'mr-IN', 'ta-IN'])
def test_question_is_translated_before_synthesis(language):
    client = Mock()
    client.text.translate.return_value = SimpleNamespace(translated_text='Translated question')
    client.text_to_speech.convert_stream.return_value = iter([b'audio'])
    assert speak_question('What happened?', 'key', language, client=client) == b'audio'
    client.text.translate.assert_called_once_with(input='What happened?', source_language_code='en-IN',
                                                  target_language_code=language, model='sarvam-translate:v1')
    request = client.text_to_speech.convert_stream.call_args.kwargs
    assert request['text'] == 'Translated question'
    assert request['language_code'] == language
    assert request['speaker'] == LANGUAGES[language][1]


def test_failed_translation_never_speaks_english_as_fallback():
    client = Mock()
    client.text.translate.return_value = SimpleNamespace(translated_text=' ')
    with pytest.raises(VoiceError):
        speak_question('What happened?', 'key', 'hi-IN', client=client)
    client.text_to_speech.convert_stream.assert_not_called()
