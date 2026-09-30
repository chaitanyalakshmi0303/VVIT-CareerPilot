"""
PlacementPrep OS - Centralized Language & Regional Speech Configuration
Defines exact BCP-47 locales, Unicode validation ranges, and language contracts.
"""

from typing import Dict, List, Any, Optional

SUPPORTED_LANGUAGES: List[Dict[str, Any]] = [
    {
        "code": "te-IN",
        "name": "Telugu",
        "nativeName": "తెలుగు",
        "ttsLocale": "te-IN",
        "recognitionLocale": "te-IN",
        "script_range": (0x0C00, 0x0C7F)
    },
    {
        "code": "hi-IN",
        "name": "Hindi",
        "nativeName": "हिन्दी",
        "ttsLocale": "hi-IN",
        "recognitionLocale": "hi-IN",
        "script_range": (0x0900, 0x097F)
    },
    {
        "code": "en-IN",
        "name": "English",
        "nativeName": "English (India)",
        "ttsLocale": "en-IN",
        "recognitionLocale": "en-IN",
        "script_range": (0x0020, 0x007F)
    },
    {
        "code": "ta-IN",
        "name": "Tamil",
        "nativeName": "தமிழ்",
        "ttsLocale": "ta-IN",
        "recognitionLocale": "ta-IN",
        "script_range": (0x0B80, 0x0BFF)
    },
    {
        "code": "kn-IN",
        "name": "Kannada",
        "nativeName": "ಕನ್ನಡ",
        "ttsLocale": "kn-IN",
        "recognitionLocale": "kn-IN",
        "script_range": (0x0C80, 0x0CFF)
    },
    {
        "code": "ml-IN",
        "name": "Malayalam",
        "nativeName": "മലയാളം",
        "ttsLocale": "ml-IN",
        "recognitionLocale": "ml-IN",
        "script_range": (0x0D00, 0x0D7F)
    },
    {
        "code": "bn-IN",
        "name": "Bengali",
        "nativeName": "বাংলা",
        "ttsLocale": "bn-IN",
        "recognitionLocale": "bn-IN",
        "script_range": (0x0980, 0x09FF)
    },
    {
        "code": "mr-IN",
        "name": "Marathi",
        "nativeName": "मराठी",
        "ttsLocale": "mr-IN",
        "recognitionLocale": "mr-IN",
        "script_range": (0x0900, 0x097F)
    },
    {
        "code": "gu-IN",
        "name": "Gujarati",
        "nativeName": "ગુજરાતી",
        "ttsLocale": "gu-IN",
        "recognitionLocale": "gu-IN",
        "script_range": (0x0A80, 0x0AFF)
    },
    {
        "code": "pa-IN",
        "name": "Punjabi",
        "nativeName": "ਪੰਜਾਬੀ",
        "ttsLocale": "pa-IN",
        "recognitionLocale": "pa-IN",
        "script_range": (0x0A00, 0x0A7F)
    },
    {
        "code": "or-IN",
        "name": "Odia",
        "nativeName": "ଓଡ଼ିଆ",
        "ttsLocale": "or-IN",
        "recognitionLocale": "or-IN",
        "script_range": (0x0B00, 0x0B7F)
    },
    {
        "code": "ur-IN",
        "name": "Urdu",
        "nativeName": "اردو",
        "ttsLocale": "ur-IN",
        "recognitionLocale": "ur-IN",
        "script_range": (0x0600, 0x06FF)
    },
    {
        "code": "as-IN",
        "name": "Assamese",
        "nativeName": "অসমীয়া",
        "ttsLocale": "as-IN",
        "recognitionLocale": "as-IN",
        "script_range": (0x0980, 0x09FF)
    },
    {
        "code": "auto",
        "name": "Auto Detect",
        "nativeName": "🌐 Auto Detect",
        "ttsLocale": "te-IN",
        "recognitionLocale": "te-IN",
        "script_range": None
    }
]

LANGUAGE_MAP: Dict[str, Dict[str, Any]] = {lang["name"]: lang for lang in SUPPORTED_LANGUAGES}

def get_language_names() -> List[str]:
    return [lang["name"] for lang in SUPPORTED_LANGUAGES]

def get_language_config(lang_name: str) -> Dict[str, Any]:
    return LANGUAGE_MAP.get(lang_name, LANGUAGE_MAP["English"])

def get_locale_code(lang_name: str) -> str:
    cfg = get_language_config(lang_name)
    return cfg.get("ttsLocale", "en-IN")

def text_has_script_characters(text: str, lang_name: str) -> bool:
    """Verifies that the text actually contains characters from the target script."""
    cfg = get_language_config(lang_name)
    rng = cfg.get("script_range")
    if not rng or lang_name in ("English", "Auto Detect"):
        return True
    return any(rng[0] <= ord(ch) <= rng[1] for ch in text)

def detect_script_language(text: str) -> str:
    """Detects primary Indic script language based on Unicode codepoints."""
    if not text:
        return "English"
    counts: Dict[str, int] = {}
    for ch in text:
        cp = ord(ch)
        for lang in SUPPORTED_LANGUAGES:
            rng = lang.get("script_range")
            if rng and rng[0] <= cp <= rng[1]:
                counts[lang["name"]] = counts.get(lang["name"], 0) + 1
                break
    if not counts:
        return "English"
    return max(counts.items(), key=lambda kv: kv[1])[0]