"""Reminder service — persistent storage, CRUD, background checker, desktop notifications."""

import asyncio
import json
import logging
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Optional

from app.core.config import REMINDERS_FILE
from app.core.events import manager

logger = logging.getLogger("reminder_service")


class ReminderService:
    def __init__(self):
        self._reminders: list[dict] = []
        self._load()

    # ── Persistence ────────────────────────────────────────────────

    def _load(self):
        if REMINDERS_FILE.exists() and REMINDERS_FILE.stat().st_size > 0:
            try:
                data = json.loads(REMINDERS_FILE.read_text(encoding="utf-8"))
                self._reminders = data.get("reminders", [])
                logger.info(f"Loaded {len(self._reminders)} reminders")
            except Exception as e:
                logger.warning(f"Failed to load reminders: {e}")
                self._reminders = []
        else:
            self._reminders = []

    def _save(self):
        REMINDERS_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = REMINDERS_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"reminders": self._reminders}, indent=2), encoding="utf-8")
        tmp.replace(REMINDERS_FILE)

    # ── Broadcast helper ───────────────────────────────────────────

    async def _broadcast(self):
        await manager.broadcast({
            "type": "reminders_updated",
            "reminders": self._reminders,
        })

    # ── CRUD ───────────────────────────────────────────────────────

    def create(self, title: str, message: str, trigger_at: float) -> dict:
        reminder = {
            "id": uuid.uuid4().hex[:12],
            "title": title,
            "message": message,
            "trigger_at": trigger_at,
            "created_at": time.time(),
            "active": True,
            "fired": False,
        }
        self._reminders.append(reminder)
        self._save()
        return reminder

    def list_all(self) -> list[dict]:
        return list(self._reminders)

    def get(self, reminder_id: str) -> Optional[dict]:
        for r in self._reminders:
            if r["id"] == reminder_id:
                return r
        return None

    def update(self, reminder_id: str, **kwargs) -> Optional[dict]:
        reminder = self.get(reminder_id)
        if reminder is None:
            return None
        for key in ("title", "message", "trigger_at", "active"):
            if key in kwargs:
                reminder[key] = kwargs[key]
        reminder["fired"] = False
        self._save()
        return reminder

    def delete(self, reminder_id: str) -> bool:
        before = len(self._reminders)
        self._reminders = [r for r in self._reminders if r["id"] != reminder_id]
        if len(self._reminders) < before:
            self._save()
            return True
        return False

    # ── Background checker ─────────────────────────────────────────

    async def check_loop(self, interval: float = 5.0):
        while True:
            await asyncio.sleep(interval)
            now = time.time()
            for reminder in self._reminders:
                if reminder["active"] and not reminder["fired"] and reminder["trigger_at"] <= now:
                    reminder["fired"] = True
                    self._save()
                    await self._fire_notification(reminder)
                    await manager.broadcast({
                        "type": "reminder_fired",
                        "reminder": reminder,
                    })

    async def _fire_notification(self, reminder: dict):
        title = reminder["title"]
        message = reminder["message"]

        # Strategy 1: notify-send (Linux desktop / WSLg with notification daemon)
        if shutil.which("notify-send"):
            try:
                proc = await asyncio.create_subprocess_exec(
                    "notify-send", title, message,
                    "--app-name=conv",
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                await proc.wait()
                logger.info(f"Notification via notify-send: {title}")
                return
            except Exception:
                logger.debug("notify-send failed, trying next method")

        # Strategy 2: Windows popup via PowerShell (works in WSL)
        if shutil.which("powershell.exe"):
            try:
                safe_title = title.replace("'", "''")
                safe_msg = message.replace("'", "''")
                proc = await asyncio.create_subprocess_exec(
                    "powershell.exe",
                    "-Command",
                    f"(New-Object -ComObject WScript.Shell).Popup('{safe_msg}',5,'{safe_title}',0) | Out-Null",
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                await proc.wait()
                logger.info(f"Notification via PowerShell popup: {title}")
                return
            except Exception:
                logger.debug("PowerShell notification failed, trying next method")

        # Strategy 3: zenity info dialog (last resort)
        if shutil.which("zenity"):
            try:
                proc = await asyncio.create_subprocess_exec(
                    "zenity", "--info",
                    f"--title={title}",
                    f"--text={message}",
                    "--timeout=5",
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                await proc.wait()
                logger.info(f"Notification via zenity: {title}")
                return
            except Exception:
                logger.debug("zenity notification failed")

        logger.warning("No notification system available (install libnotify-bin for desktop notifications)")


# Singleton
_service: Optional[ReminderService] = None


def get_reminder_service() -> ReminderService:
    global _service
    if _service is None:
        _service = ReminderService()
    return _service
