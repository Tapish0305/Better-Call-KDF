"""Sarvam speech boundary. Audio and credentials never enter exported case state."""
import io
import wave

from sarvamai import SarvamAI

LANGUAGES = {
    'hi-IN': ('हिन्दी · Hindi', 'shubh_hi_customer'),
    'en-IN': ('English', 'shubh_en_narration_gentle'),
    'bn-IN': ('বাংলা · Bengali', 'roopa_bn_conversational'),
    'mr-IN': ('मराठी · Marathi', 'ishita_mr_conversational'),
    'ta-IN': ('தமிழ் · Tamil', 'gokul_ta_narration'),
}


class VoiceError(ValueError):
    pass


def transcribe_audio(audio: bytes, api_key: str, language: str = 'unknown', *, client=None) -> str:
    # Keep synchronous requests short; longer narratives can be appended in parts.
    try:
        with wave.open(io.BytesIO(audio), 'rb') as recording:
            duration = recording.getnframes() / recording.getframerate()
    except (wave.Error, EOFError):
        raise VoiceError('Please record a valid WAV audio message.') from None
    if not 0 < duration <= 29:
        raise VoiceError('Record up to 29 seconds per clip. Add longer answers in several clips.')
    client = client or SarvamAI(api_subscription_key=api_key, timeout=45)
    result = client.speech_to_text.transcribe(
        file=('answer.wav', audio, 'audio/wav'), model='saaras:v4',
        language_code=language, mode='transcribe',
    )
    transcript = (result.transcript or '').strip()
    if not transcript:
        raise VoiceError('No speech was recognised. Please record again or type your answer.')
    return transcript


def speak_question(text: str, api_key: str, language: str = 'en-IN', *, client=None) -> bytes:
    if language not in LANGUAGES:
        raise VoiceError('Please select a supported conversation language.')
    client = client or SarvamAI(api_subscription_key=api_key, timeout=45)
    if language != 'en-IN':
        translated = client.text.translate(
            input=text, source_language_code='en-IN', target_language_code=language,
            model='sarvam-translate:v1',
        )
        text = (translated.translated_text or '').strip()
        if not text:
            raise VoiceError('The question could not be translated. Please try again.')
    audio = b''.join(client.text_to_speech.convert_stream(
        text=text, language_code=language, speaker=LANGUAGES[language][1],
        model='bulbul:v4-flash', pace=1, speech_sample_rate=24000,
        output_audio_codec='mp3',
    ))
    if not audio:
        raise VoiceError('No audio was returned. Please try again.')
    return audio
