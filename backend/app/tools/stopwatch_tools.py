"""Stopwatch tools — agent can start, stop, check, and set the stopwatch."""

from app.services.stopwatch_service import get_stopwatch_service


def _fmt(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    if h:
        return f"{h}h {m}m {s:.1f}s"
    if m:
        return f"{m}m {s:.1f}s"
    return f"{s:.1f}s"


def stopwatch_start() -> str:
    svc = get_stopwatch_service()
    svc.start()
    return f"Stopwatch started."


def stopwatch_stop() -> str:
    svc = get_stopwatch_service()
    elapsed = svc.current_elapsed()
    svc.stop()
    return f"Stopwatch stopped at {_fmt(elapsed)}."


def stopwatch_check() -> str:
    svc = get_stopwatch_service()
    elapsed = svc.current_elapsed()
    running = svc.state()["running"]
    status = "running" if running else "stopped"
    return f"Stopwatch: {_fmt(elapsed)} ({status})."


def stopwatch_set(seconds: float = 0.0) -> str:
    svc = get_stopwatch_service()
    svc.set(seconds)
    return f"Stopwatch set to {_fmt(seconds)}."
