import threading


class _RuntimeFlags:
    def __init__(self):
        self._lock = threading.Lock()
        self._flags = {}

    def set(self, key: str, value: bool):
        with self._lock:
            self._flags[key] = bool(value)

    def set_any(self, key: str, value):
        with self._lock:
            self._flags[key] = value

    def get(self, key: str, default: bool = False) -> bool:
        with self._lock:
            return bool(self._flags.get(key, default))

    def get_any(self, key: str, default=None):
        with self._lock:
            return self._flags.get(key, default)

    def dump(self) -> dict:
        with self._lock:
            return dict(self._flags)


flags = _RuntimeFlags()


