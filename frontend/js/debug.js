"use strict";

/* ── Debug / Inspection View ──────────────────────────────────── */

let debugLog = [];
let debugEventLog = [];

function initDebugView() {
  renderApiLog();
  renderContextInspector();
  renderTokenUsage();
  renderToolFlow();
  renderModelInfo();
  renderRawEvents();
}

/* ── API Log ──────────────────────────────────────────────────── */

function logApiCall(method, url, status, duration, requestBody, responseBody) {
  debugLog.push({
    time: new Date().toLocaleTimeString(),
    method, url, status, duration,
    requestBody: typeof requestBody === 'string' ? requestBody : JSON.stringify(requestBody),
    responseBody: typeof responseBody === 'string' ? responseBody : JSON.stringify(responseBody),
  });
  if (debugLog.length > 200) debugLog.splice(0, debugLog.length - 200);
}

function renderApiLog() {
  const el = $('dbgview-api-log');
  if (!el) return;
  if (debugLog.length === 0) {
    el.innerHTML = '<div class="text-[10px] text-slate-600 italic">No API calls logged yet.</div>';
    return;
  }
  let html = '';
  for (const entry of debugLog.slice(-50).reverse()) {
    const color = entry.status >= 400 ? 'text-rose-400' : entry.status >= 300 ? 'text-amber-400' : 'text-emerald-400';
    html += `<div class="text-[9px] font-mono leading-relaxed">
      <span class="text-slate-600">${entry.time}</span>
      <span class="${color}">${entry.method}</span>
      <span class="text-slate-400">${escapeHtml(entry.url)}</span>
      <span class="${color}">${entry.status}</span>
      <span class="text-slate-600">${entry.duration ? entry.duration.toFixed(1) + 's' : ''}</span>
    </div>`;
  }
  el.innerHTML = html;
}

/* ── Context Inspector ────────────────────────────────────────── */

async function renderContextInspector() {
  const el = $('dbgview-context');
  if (!el) return;
  try {
    const r = await fetch('/api/session/history');
    const d = await r.json();
    const history = d.history || [];
    let html = '<div class="text-[10px] text-slate-500 mb-2">Chat history shown below. Each assistant message includes the context sent.</div>';
    html += `<div class="text-[9px] text-slate-600 mb-2">${history.length} messages in history</div>`;
    for (const msg of history.slice(-10)) {
      const role = msg.role || 'unknown';
      const content = msg.content || '';
      const color = role === 'user' ? 'text-indigo-400' : 'text-emerald-400';
      html += `<div class="glass rounded p-2 mb-1">
        <div class="${color} text-[9px] font-bold mb-1">${role}</div>
        <div class="text-[9px] text-slate-400 font-mono whitespace-pre-wrap break-all max-h-20 overflow-y-auto">${escapeHtml(content.slice(0, 500))}</div>
        <div class="text-[8px] text-slate-600 mt-0.5">${content.length} chars</div>
      </div>`;
    }
    el.innerHTML = html;
  } catch(_) {
    el.innerHTML = '<div class="text-[10px] text-slate-600">Failed to load context.</div>';
  }
}

/* ── Token Usage ──────────────────────────────────────────────── */

async function renderTokenUsage() {
  const el = $('dbgview-tokens');
  if (!el) return;
  try {
    const r = await fetch('/api/diagnostics');
    const d = await r.json();
    const history = d.history || [];
    if (history.length === 0) {
      el.innerHTML = '<div class="text-[10px] text-slate-600 italic">No token data yet.</div>';
      return;
    }
    let html = `<div class="text-[9px] text-slate-600 mb-2">Last ${history.length} generations</div>`;
    for (const entry of history.slice(-20).reverse()) {
      html += `<div class="text-[9px] font-mono text-slate-400 leading-relaxed">
        ${fmtUtc(entry.timestamp)} &mdash; ${entry.generation_time_s.toFixed(2)}s | ${entry.tokens_per_second.toFixed(1)} t/s | ${entry.token_count} tok
      </div>`;
    }
    el.innerHTML = html;
  } catch(_) {
    el.innerHTML = '<div class="text-[10px] text-slate-600">No data.</div>';
  }
}

/* ── Tool Flow ────────────────────────────────────────────────── */

function renderToolFlow() {
  const el = $('dbgview-tools');
  if (!el) return;
  el.innerHTML = '<div class="text-[10px] text-slate-600 italic">Tool flow will be populated from streaming events.</div>';
}

/* ── Model Info ───────────────────────────────────────────────── */

async function renderModelInfo() {
  const el = $('dbgview-model');
  if (!el) return;
  try {
    const r = await fetch('/api/models/active');
    const d = await r.json();
    const modelId = d.model_instance_id || 'None';
    el.innerHTML = `<div class="text-[10px] font-mono text-slate-400">Active model: <span class="text-indigo-400">${escapeHtml(modelId)}</span></div>`;
  } catch(_) {
    el.innerHTML = '<div class="text-[10px] text-slate-600">Failed to load model info.</div>';
  }
}

/* ── Raw Events ───────────────────────────────────────────────── */

function logRawEvent(eventData) {
  debugEventLog.push({
    time: new Date().toLocaleTimeString(),
    data: eventData,
  });
  if (debugEventLog.length > 500) debugEventLog.splice(0, debugEventLog.length - 500);
}

function renderRawEvents() {
  const el = $('dbgview-events');
  if (!el) return;
  if (debugEventLog.length === 0) {
    el.innerHTML = '<div class="text-[10px] text-slate-600 italic">No events yet.</div>';
    return;
  }
  let html = '';
  for (const entry of debugEventLog.slice(-100).reverse()) {
    html += `<div class="text-[8px] font-mono text-slate-500 leading-relaxed border-b border-white/5 pb-0.5 mb-0.5">
      <span class="text-slate-600">${entry.time}</span>
      <span class="text-slate-400">${escapeHtml(JSON.stringify(entry.data))}</span>
    </div>`;
  }
  el.innerHTML = html;
}
