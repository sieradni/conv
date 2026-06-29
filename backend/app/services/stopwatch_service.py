"""Stopwatch service — persistent stopwatch with start, stop, check, and reset."""

import json
import logging
import time
from typing import Optional

from app.core.config import STOPWATCH_FILE

logger = logging.getLogger("stopwatch_service")


class StopwatchService:
    def __init__(self):
        self._running: bool = False
        self._started_at: float = 0.0
        self._elapsed: float = 0.0
        self._load()

    # ── Persistence ────────────────────────────────────────────────

    def _load(self):
        if STOPWATCH_FILE.exists() and STOPWATCH_FILE.stat().st_size > 0:
            try:
                data = json.loads(STOPWATCH_FILE.read_text(encoding="utf-8"))
                self._running = data.get("running", False)
                self._started_at = data.get("started_at", 0.0)
                self._elapsed = data.get("elapsed", 0.0)
                logger.info(f"Loaded stopwatch (running={self._running}, elapsed={self._elapsed:.1f}s)")
            except Exception as e:
                logger.warning(f"Failed to load stopwatch: {e}")

    def _save(self):
        STOPWATCH_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "running": self._running,
            "started_at": self._started_at,
            "elapsed": self._elapsed,
        }
        tmp = STOPWATCH_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(STOPWATCH_FILE)

    # ── Operations ─────────────────────────────────────────────────

    def current_elapsed(self) -> float:
        if self._running:
            return self._elapsed + (time.time() - self._started_at)
        return self._elapsed

    def start(self) -> dict:
        self._running = True
        self._started_at = time.time()
        self._save()
        return self.state()

    def stop(self) -> dict:
        if self._running:
            self._elapsed += time.time() - self._started_at
            self._running = False
            self._started_at = 0.0
            self._save()
        return self.state()

    def reset(self, set_to: float = 0.0) -> dict:
        self._running = False
        self._started_at = 0.0
        self._elapsed = set_to
        self._save()
        return self.state()

    def set(self, seconds: float) -> dict:
        self._elapsed = max(0.0, seconds)
        self._save()
        return self.state()

    def state(self) -> dict:
        return {
            "running": self._running,
            "started_at": self._started_at if self._running else 0.0,
            "elapsed": self._elapsed,
        }


# Singleton
_service: Optional[StopwatchService] = None


def get_stopwatch_service() -> StopwatchService:
    global _service
    if _service is None:
        _service = StopwatchService()
    return _service
