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
        text = re.sub(r"\\times", 'x', text)

        # Collapse multiple spaces/newlines
        text = re.sub(r"\s+", ' ', text).strip()
        return text
    except Exception:
        return text


