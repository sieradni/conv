"""Reminder tools — agent can create, list, update, and delete reminders."""

import time
from app.services.reminder_service import get_reminder_service


def create_reminder(title: str, message: str, trigger_at: float | None = None, trigger_in: float | None = None) -> str:
    svc = get_reminder_service()
    if trigger_at is None and trigger_in is not None:
        trigger_at = time.time() + trigger_in
    if trigger_at is None:
        return "Error: provide either trigger_at (epoch) or trigger_in (seconds from now)"
    reminder = svc.create(title=title, message=message, trigger_at=trigger_at)
    return f"Created reminder {reminder['id']}: {title}"


def list_reminders() -> str:
    svc = get_reminder_service()
    reminders = svc.list_all()
    if not reminders:
        return "No reminders."
    lines = ["Reminders:"]
    for r in reminders:
        status = "🔔 active" if r["active"] and not r["fired"] else "✅ fired" if r["fired"] else "⏸ inactive"
        lines.append(f"  [{r['id']}] {r['title']} — {r['message'][:60]} — {status}")
    return "\n".join(lines)


def update_reminder(id: str, title: str | None = None, message: str | None = None, trigger_at: float | None = None) -> str:
    svc = get_reminder_service()
    kwargs = {}
    if title is not None:
        kwargs["title"] = title
    if message is not None:
        kwargs["message"] = message
    if trigger_at is not None:
        kwargs["trigger_at"] = trigger_at
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
