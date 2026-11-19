"""Sarvam AI speech-to-text / text-to-speech wrapper.

Endpoints and fields verified against docs.sarvam.ai on 2026-11-19:
  POST https://api.sarvam.ai/speech-to-text   (multipart/form-data)
  POST https://api.sarvam.ai/text-to-speech   (application/json)
Auth header for both: "api-subscription-key: <key>" (no Bearer prefix).

If SARVAM_API_KEY is missing or any call fails, every function here
returns None so the caller falls back to typed input / text output --
the demo must never break because of voice.
"""
import base64
import os

import requests

STT_URL = "https://api.sarvam.ai/speech-to-text"
TTS_URL = "https://api.sarvam.ai/text-to-speech"
STT_MODEL = os.environ.get("SARVAM_STT_MODEL", "saaras:v4")
TTS_MODEL = os.environ.get("SARVAM_TTS_MODEL", "bulbul:v3")

# TTS requires one of these explicit language codes (no "auto").
SUPPORTED_TTS_LANGS = {"bn-IN", "en-IN", "gu-IN", "hi-IN", "kn-IN", "ml-IN", "mr-IN", "od-IN", "pa-IN", "ta-IN", "te-IN"}


def has_key():
    return bool(os.environ.get("SARVAM_API_KEY"))


def speech_to_text(audio_bytes, filename="audio.wav", language_code="unknown"):
    """Returns {"transcript": str, "language_code": str|None} or None on failure/missing key."""
    key = os.environ.get("SARVAM_API_KEY")
    if not key or not audio_bytes:
        return None
    try:
        files = {"file": (filename, audio_bytes, "audio/wav")}
        data = {"model": STT_MODEL, "mode": "transcribe", "language_code": language_code}
        resp = requests.post(
            STT_URL, headers={"api-subscription-key": key}, files=files, data=data, timeout=20,
        )
        resp.raise_for_status()
        body = resp.json()
        return {"transcript": body.get("transcript", ""), "language_code": body.get("language_code")}
    except Exception:
        return None


def _normalize_lang(language_code):
    if language_code in SUPPORTED_TTS_LANGS:
        return language_code
    # best-effort map from a bare 2-letter code or something unexpected to a supported one
    short = (language_code or "")[:2].lower()
    mapping = {"hi": "hi-IN", "en": "en-IN", "bn": "bn-IN", "gu": "gu-IN", "kn": "kn-IN",
               "ml": "ml-IN", "mr": "mr-IN", "pa": "pa-IN", "ta": "ta-IN", "te": "te-IN"}
    return mapping.get(short, "hi-IN")


def text_to_speech(text, language_code="hi-IN"):
    """Returns raw WAV bytes, or None on failure/missing key."""
    key = os.environ.get("SARVAM_API_KEY")
    if not key or not text:
        return None
    try:
        payload = {
            "text": text[:2500],
            "language_code": _normalize_lang(language_code),
            "model": TTS_MODEL,
            "output_audio_codec": "wav",
        }
        resp = requests.post(
            TTS_URL, headers={"api-subscription-key": key, "Content-Type": "application/json"},
            json=payload, timeout=20,
        )
        resp.raise_for_status()
        audios = resp.json().get("audios") or []
        if not audios:
            return None
        return base64.b64decode(audios[0])
    except Exception:
        return None
