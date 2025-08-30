import re

TAG_PATTERNS = [
    r"SentenceType\.[A-Z]+",
    r"\{\"suggest\"[\s\S]*\}",  # crude JSON-like removal for inline suggestions
]


def sanitize_for_tts(text: str) -> str:
    """Basic sanitization to remove tags/inline JSON and LaTeX delimiters for TTS."""
    try:
        # Remove common tags
        for p in TAG_PATTERNS:
            text = re.sub(p, '', text, flags=re.IGNORECASE)

        # Remove LaTeX inline delimiters \( \), \[ \], $ $ and common commands
        text = re.sub(r"\\\(|\\\)|\\\[|\\\]|\$", '', text)
        text = re.sub(r"\\frac\{([^}]*)\}\{([^}]*)\}", r"\1/\2", text)
        # Prefer spoken Japanese for multiplication symbol: use 'かける' instead of 'x' or 'エックス'
        try:
            text = re.sub(r"\\times", 'かける', text)
        except Exception:
            text = text.replace('\\times', 'かける')
        # Replace literal multiplication sign
        text = text.replace('×', 'かける')

        # Collapse multiple spaces/newlines
        text = re.sub(r"\s+", ' ', text).strip()
        return text
    except Exception:
        return text


def normalize_asr_text(text: str, correction_map: dict = None) -> str:
    try:
        if correction_map is None:
            import json, os
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            path = os.path.join(base, 'data', 'asr_corrections.json')
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    correction_map = json.load(f)
            except Exception:
                correction_map = {}

        normalized = text
        for mis, corr in (correction_map.items() if correction_map else []):
            try:
                normalized = re.sub(re.escape(mis), corr, normalized, flags=re.IGNORECASE)
            except Exception:
                pass
        return normalized
    except Exception:
        return text


