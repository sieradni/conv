"""Reminder tools — agent can create, list, update, and delete reminders."""

import time
from app.services.reminder_service import get_reminder_service


def create_reminder(title: str, message: str, trigger_at: float | None = None, trigger_in: float | None = None, info: str = "", trigger_action: str = "") -> str:
    svc = get_reminder_service()
    if trigger_at is None and trigger_in is not None:
        trigger_at = time.time() + trigger_in
    if trigger_at is None:
        return "Error: provide either trigger_at (epoch) or trigger_in (seconds from now)"
    reminder = svc.create(title=title, message=message, trigger_at=trigger_at, info=info, trigger_action=trigger_action)
    parts = [f"Created reminder {reminder['id']}: {title}"]
    if trigger_action:
        parts.append(f"(will trigger agent: {trigger_action})")
    return " ".join(parts)


def list_reminders() -> str:
    svc = get_reminder_service()
    reminders = svc.list_all()
    if not reminders:
        return "No reminders."
    lines = ["Reminders:"]
    for r in reminders:
        status = "🔔 active" if r["active"] and not r["fired"] else "✅ fired" if r["fired"] else "⏸ inactive"
        tag = ""
        if r.get("trigger_action"):
            tag = f" → agent:{r['trigger_action']}"
        lines.append(f"  [{r['id']}] {r['title']} — {r['message'][:60]}{tag} — {status}")
    return "\n".join(lines)


def update_reminder(id: str, title: str | None = None, message: str | None = None, trigger_at: float | None = None, info: str | None = None, trigger_action: str | None = None) -> str:
    svc = get_reminder_service()
    kwargs = {}
    for k, v in [("title", title), ("message", message), ("trigger_at", trigger_at), ("info", info), ("trigger_action", trigger_action)]:
        if v is not None:
            kwargs[k] = v
    if not kwargs:
        return "Error: nothing to update"
    result = svc.update(id, **kwargs)
    if result is None:
        return f"Error: reminder {id} not found"
    return f"Updated reminder {id}"


def delete_reminder(id: str) -> str:
    svc = get_reminder_service()
    if svc.delete(id):
        return f"Deleted reminder {id}"
    return f"Error: reminder {id} not found"
