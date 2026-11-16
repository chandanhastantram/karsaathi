"""Supported languages. To add one later: add it here, then add its strings to
summary.T, summary.MONTHS and summary.NUDGE (and the frontend LANGS list).

Planned next: bn, te, mr, ta, ur, gu, ml, or, pa, as (see README)."""

LANGUAGES = {
    "en": {"name": "English", "native": "English"},
    "hi": {"name": "Hindi", "native": "हिन्दी"},
    "kn": {"name": "Kannada", "native": "ಕನ್ನಡ"},
}

SPEECH_LOCALE = {"en": "en-IN", "hi": "hi-IN", "kn": "kn-IN"}


def supported(lang: str) -> str:
    return lang if lang in LANGUAGES else "en"
