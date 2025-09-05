import os
from typing import Set

_DICT_SET: Set[str] = set()


def load_dict(path: str):
    global _DICT_SET
    s = set()
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                w = line.strip()
                if not w:
                    continue
                s.add(w)
    except Exception:
        # silently ignore missing file in production
        pass
    _DICT_SET = s


def contains(word: str) -> bool:
    return word in _DICT_SET


def initialize_default():
    # default path relative to project
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base, 'data', 'japanese_top1000.txt')
    load_dict(path)


# initialize at import time
initialize_default()



