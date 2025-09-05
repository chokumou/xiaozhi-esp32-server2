import os
from typing import Optional, List

_TRIGGERS = []
_TOPICS = []


def _load_lines(path: str) -> List[str]:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return [l.strip() for l in f if l.strip()]
    except Exception:
        return []


def initialize():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tpath = os.path.join(base, 'data', 'memory_triggers.txt')
    ppath = os.path.join(base, 'data', 'memory_topics.txt')
    global _TRIGGERS, _TOPICS
    _TRIGGERS = _load_lines(tpath)
    _TOPICS = _load_lines(ppath)


def check_trigger_and_topic(text: str) -> Optional[tuple]:
    """Return (trigger, topic) if any trigger+topic pair is detected in text."""
    if not text:
        return None
    txt = text
    for trig in _TRIGGERS:
        if trig in txt:
            for top in _TOPICS:
                if top in txt:
                    return (trig, top)
            # if trigger present but no explicit topic, return trigger with None
            return (trig, None)
    return None


# initialize on import
initialize()



