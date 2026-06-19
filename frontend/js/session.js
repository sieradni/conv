"use strict";

/* ── Session management ───────────────────────────────────────── */

async function initSession() {
  try {
    const r = await fetch('/api/session');
    const d = await r.json();
    window.sessionId = d.session_id;
  } catch(_) {
    window.sessionId = 'default';
  }
  const label = $('session-label');
  if (label) label.textContent = window.sessionId;
  const settingsEl = $('settings-session');
  if (settingsEl) settingsEl.textContent = window.sessionId;
}

let historyLoaded = false;

async function loadChatHistory() {
  if (historyLoaded) return;
  historyLoaded = true;
  try {
    const r = await fetch('/api/session/history');
    const d = await r.json();
    const history = d.history || [];
    for (const msg of history) {
      if (msg.role === 'user') {
        addMessage(`you: ${msg.content}`, 'indigo-400');
      } else if (msg.role === 'assistant') {
        addResponseMsg(msg.content, 'emerald-400');
      }
    }
  } catch(_) {}
}
