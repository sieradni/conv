"use strict";

/* ── Debug / Inspection View ──────────────────────────────────── */

let debugLog = [];
let debugEventLog = [];

function initDebugView() {
  renderApiLog();
  renderContextInspector();
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
  const active = $('dbgview-api-log');
  if (active && active.offsetParent !== null) renderApiLog();
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
    const uid = 'api-' + Math.random().toString(36).slice(2,6);
    html += `<div class="text-[9px] font-mono leading-relaxed cursor-pointer hover:bg-white/5" onclick="document.getElementById('${uid}').classList.toggle('hidden')">
      <span class="text-slate-600">${entry.time}</span>
      <span class="${color}">${entry.method}</span>
      <span class="text-slate-400">${escapeHtml(entry.url)}</span>
      <span class="${color}">${entry.status}</span>
      <span class="text-slate-600">${entry.duration ? entry.duration.toFixed(1) + 's' : ''}</span>
      <div id="${uid}" class="hidden mt-1 pl-2 border-l border-white/5">
        <div class="text-[7px] text-amber-500/60">REQUEST</div>
        <div class="text-[7px] text-slate-500 font-mono whitespace-pre-wrap break-all max-h-24 overflow-y-auto">${escapeHtml(entry.requestBody || '(empty)')}</div>
        <div class="text-[7px] text-emerald-500/60 mt-1">RESPONSE</div>
        <div class="text-[7px] text-slate-500 font-mono whitespace-pre-wrap break-all max-h-24 overflow-y-auto">${escapeHtml(entry.responseBody || '(empty)')}</div>
      </div>
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
    let html = `<div class="text-[9px] text-slate-600 mb-2">${history.length} messages</div>`;
    for (const msg of history.slice(-15)) {
      const role = msg.role || 'unknown';
      const content = msg.content || '';
      const color = role === 'user' ? 'text-indigo-400' : 'text-emerald-400';
      html += `<div class="border-b border-white/5 py-1.5">
        <div class="flex items-center gap-2">
          <span class="text-[9px] font-bold ${color} uppercase">${role}</span>
          <span class="text-[8px] text-slate-600">(${content.length} chars)</span>
        </div>
        <div class="text-[9px] text-slate-400 font-mono whitespace-pre-wrap break-all max-h-24 overflow-y-auto mt-0.5">${escapeHtml(content.substring(0, 2000))}${content.length > 2000 ? '<span class="text-slate-600"> ...</span>' : ''}</div>`;
      // Show full LLM context for assistant messages
      if (role === 'assistant' && msg.context) {
        try {
          const ctx = JSON.parse(msg.context);
          html += `<div class="mt-1">
            <span class="text-[8px] text-indigo-400/60 cursor-pointer hover:text-indigo-400" onclick="this.nextElementSibling.classList.toggle('hidden')">▸ LLM context (${ctx.length} msgs)</span>
            <div class="hidden mt-1">`;
          for (const c of ctx) {
            const cRole = c.role || '?';
            const isSystem = cRole === 'system';
            const cColor = isSystem ? 'text-amber-400' : cRole === 'user' ? 'text-indigo-400' : 'text-slate-500';
            const label = isSystem ? 'system prompt' : cRole;
            const cContent = c.content || '';
            html += `<div class="mb-1.5 pl-2 border-l border-white/5">
              <span class="text-[7px] font-bold ${cColor}">${label}</span>
              <span class="text-[7px] text-slate-600">(${cContent.length} chars)</span>
              <div class="text-[7px] text-slate-500 font-mono whitespace-pre-wrap break-all max-h-32 overflow-y-auto mt-0.5">${escapeHtml(cContent.substring(0, 5000))}${cContent.length > 5000 ? '<span class="text-slate-600"> ...</span>' : ''}</div>
            </div>`;
          }
          html += `</div></div>`;
        } catch(_) {}
      }
      html += `</div>`;
    }
    el.innerHTML = html;
  } catch(_) {
    el.innerHTML = '<div class="text-[10px] text-slate-600">Failed to load context.</div>';
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
  const active = $('dbgview-events');
  if (active && active.offsetParent !== null) renderRawEvents();
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
    const evtType = entry.data.type || 'unknown';
    const typeColor = evtType === 'chat_done' ? 'text-emerald-400' : evtType === 'reasoning_done' ? 'text-amber-400' : evtType === 'tool_use' ? 'text-rose-400' : 'text-slate-400';
    const uid = 'evt-' + Math.random().toString(36).slice(2,6);
    html += `<div class="text-[8px] font-mono leading-relaxed border-b border-white/5 pb-0.5 mb-0.5 cursor-pointer hover:bg-white/5" onclick="document.getElementById('${uid}').classList.toggle('hidden')">
      <span class="text-slate-600">${entry.time}</span>
      <span class="${typeColor}">${evtType}</span>
      <div id="${uid}" class="hidden mt-0.5 pl-2 border-l border-white/5">
        <div class="text-[7px] text-slate-500 font-mono whitespace-pre-wrap break-all max-h-48 overflow-y-auto">${escapeHtml(JSON.stringify(entry.data, null, 2))}</div>
      </div>
    </div>`;
  }
  el.innerHTML = html;
}
