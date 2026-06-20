"use strict";

/* ── Notes view switching (notes / reminders subtabs) ───────── */

function switchNotesView(view) {
  document.querySelectorAll('[id^="notesview-"]').forEach(p => p.classList.add('hidden'));
  const panel = $(`notesview-${view}`);
  if (panel) panel.classList.remove('hidden');
  document.querySelectorAll('.notes-subtab').forEach(t => {
    const isActive = t.dataset.notesview === view;
    t.className = isActive
      ? 'notes-subtab px-3 py-1 text-[9px] font-bold uppercase tracking-widest rounded-md bg-indigo-500/10 text-indigo-400 border border-indigo-500/20'
      : 'notes-subtab px-3 py-1 text-[9px] font-bold uppercase tracking-widest rounded-md text-slate-500 hover:text-slate-300 transition';
  });
  if (view === 'reminders') loadReminders();
  if (view === 'notes') loadNotes();
}

function initNotesView() {
  document.querySelectorAll('.notes-subtab').forEach(t =>
    t.addEventListener('click', () => switchNotesView(t.dataset.notesview))
  );
}

/* ── Reminders ──────────────────────────────────────────────── */

async function loadReminders() {
  try {
    const r = await fetch('/api/reminders');
    if (!r.ok) return;
    const data = await r.json();
    renderReminders(data.reminders || []);
  } catch (_) {}
}

function renderReminders(reminders) {
  const list = $('reminder-list');
  const count = $('reminder-count');
  if (!list) return;
  const activeCount = reminders.filter(r => r.active && !r.fired).length;
  if (count) count.textContent = `${reminders.length} total, ${activeCount} active`;

  if (reminders.length === 0) {
    list.innerHTML = '<div class="text-slate-600 italic text-[11px] text-center py-8">No reminders yet. Ask the agent to set one, or create below.</div>';
    return;
  }

  list.innerHTML = reminders.map(r => {
    const now = Date.now() / 1000;
    const isPast = r.trigger_at <= now;
    let statusBadge, statusClass;
    if (r.fired) {
      statusBadge = 'fired';
      statusClass = 'bg-slate-600/20 text-slate-400 border-slate-600/30';
    } else if (!r.active) {
      statusBadge = 'inactive';
      statusClass = 'bg-slate-600/20 text-slate-500 border-slate-600/20';
    } else if (isPast) {
      statusBadge = 'missed';
      statusClass = 'bg-amber-600/20 text-amber-400 border-amber-600/30';
    } else {
      statusBadge = 'active';
      statusClass = 'bg-emerald-600/20 text-emerald-400 border-emerald-600/30';
    }

    const timeStr = fmtReminderTime(r.trigger_at);
    const icon = r.trigger_at > now + 86400 ? '🔔' : '⏰';

    return `<div class="flex items-start gap-2.5 bg-black/30 border border-white/5 rounded-lg px-3 py-2 slide-up">
      <span class="mt-0.5 text-xs">${icon}</span>
      <div class="flex-1 min-w-0">
        <div class="flex items-center gap-2 mb-0.5">
          <span class="text-[11px] font-semibold text-slate-200 truncate">${escapeHtml(r.title)}</span>
          <span class="badge ${statusClass}">${statusBadge}</span>
        </div>
        <p class="text-[10px] text-slate-500 leading-relaxed truncate">${escapeHtml(r.message)}</p>
        <span class="text-[9px] text-slate-600 font-mono">${timeStr}</span>
      </div>
      <button onclick="deleteReminderUI('${r.id}')" class="shrink-0 px-1.5 py-0.5 rounded text-[10px] text-slate-600 hover:text-rose-400 hover:bg-rose-600/10 transition" title="Delete reminder">&times;</button>
    </div>`;
  }).join('');
}

function fmtReminderTime(ts) {
  const now = Date.now() / 1000;
  const diff = ts - now;
  if (diff <= 0) {
    return `was due ${fmtRelative(-diff)} ago`;
  }
  return `in ${fmtRelative(diff)} \u00b7 ${new Date(ts * 1000).toLocaleString()}`;
}

function fmtRelative(seconds) {
  if (seconds < 60) return '<1m';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
  const days = Math.floor(seconds / 86400);
  return `${days}d ${Math.floor((seconds % 86400) / 3600)}h`;
}

async function deleteReminderUI(id) {
  try {
    const r = await fetch(`/api/reminders/${id}`, { method: 'DELETE' });
    if (r.ok) loadReminders();
  } catch (_) {}
}

async function createReminderUI() {
  const title = $('reminder-title-input');
  const message = $('reminder-msg-input');
  const timeEl = $('reminder-time-input');
  if (!title || !message || !timeEl) return;
  const t = title.value.trim();
  const m = message.value.trim();
  const dt = timeEl.value;
  if (!t || !dt) return;
  const trigger_at = new Date(dt).getTime() / 1000;
  if (isNaN(trigger_at) || trigger_at <= Date.now() / 1000) return;
  try {
    const r = await fetch('/api/reminders', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: t, message: m || t, trigger_at }),
    });
    if (r.ok) {
      title.value = '';
      message.value = '';
      timeEl.value = '';
      loadReminders();
    }
  } catch (_) {}
}

function refreshRemindersFromEvent(data) {
  if (data.type === 'reminder_fired' && data.reminder) {
    const msg = data.reminder.title + (data.reminder.message ? ': ' + data.reminder.message : '');
    showToast(`\u23f0 ${msg}`);
  }
  loadReminders();
}

/* ── Set min for datetime-local to now ──────────────────────── */

function updateReminderTimeMin() {
  const input = $('reminder-time-input');
  if (input) {
    const now = new Date();
    now.setMinutes(now.getMinutes() + 1);
    input.min = now.toISOString().slice(0, 16);
  }
}
setInterval(updateReminderTimeMin, 30000);
