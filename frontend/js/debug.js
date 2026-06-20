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
  const active = $('dbgview-api-log');
  if (active && active.offsetParent !== null) renderApiLog();
}

function renderApiLog() {
  const el = $('dbgview-api-log');
  if (!el) return;

  // Save expanded state + scroll positions
  const expanded = new Set();
  const scrollPos = {};
  el.querySelectorAll('[id^="api-"]').forEach(d => {
    const idx = parseInt(d.id.replace('api-', ''), 10);
    if (!isNaN(idx)) {
      if (!d.classList.contains('hidden')) expanded.add(idx);
      d.querySelectorAll('[class*="overflow-y-auto"]').forEach((c, ci) => {
        scrollPos[`api-${idx}-${ci}`] = c.scrollTop;
      });
    }
  });

  if (debugLog.length === 0) {
    el.innerHTML = '<div class="text-[10px] text-slate-600 italic">No API calls logged yet.</div>';
    return;
  }

  let left = '';
  let right = '';
  for (let i = debugLog.length - 1; i >= 0; i--) {
    const entry = debugLog[i];
    const color = entry.status >= 400 ? 'text-rose-400' : entry.status >= 300 ? 'text-amber-400' : 'text-emerald-400';
    const isExpanded = expanded.has(i) ? '' : 'hidden';
    const isStatus = entry.method === 'GET' && !entry.url.includes('history');
    const row = `<div class="text-[9px] font-mono leading-relaxed cursor-pointer hover:bg-white/5" onclick="document.getElementById('api-${i}').classList.toggle('hidden')">
      <span class="text-slate-600">${entry.time}</span>
      <span class="${color}">${entry.method}</span>
      <span class="text-slate-400">${escapeHtml(entry.url)}</span>
      <span class="${color}">${entry.status}</span>
      <span class="text-slate-600">${entry.duration ? entry.duration.toFixed(1) + 's' : ''}</span>
      <div id="api-${i}" class="${isExpanded} mt-1 pl-2 border-l border-white/5">
        <div class="text-[7px] text-amber-500/60">REQUEST</div>
        <div class="text-[7px] text-slate-500 font-mono whitespace-pre-wrap break-all max-h-24 overflow-y-auto">${escapeHtml(entry.requestBody || '(empty)')}</div>
        <div class="text-[7px] text-emerald-500/60 mt-1">RESPONSE</div>
        <div class="text-[7px] text-slate-500 font-mono whitespace-pre-wrap break-all max-h-24 overflow-y-auto">${escapeHtml(entry.responseBody || '(empty)')}</div>
      </div>
    </div>`;
    if (isStatus) { right += row; } else { left += row; }
  }

  el.innerHTML = `<div style="display:flex;gap:8px;height:100%;min-height:0">
    <div style="flex:1;overflow-y:auto;min-height:0">
      <div class="text-[8px] text-slate-600 font-bold uppercase tracking-wider mb-1">ACTIONS</div>
      ${left}
    </div>
    <div style="flex:1;overflow-y:auto;min-height:0">
      <div class="text-[8px] text-slate-600 font-bold uppercase tracking-wider mb-1">RESOURCE / STATUS</div>
      ${right}
    </div>
  </div>`;

  // Restore scroll positions
  requestAnimationFrame(() => {
    Object.keys(scrollPos).forEach(k => {
      const parts = k.split('-');
      const elId = `${parts[0]}-${parts[1]}`;
      const ci = parseInt(parts[2], 10);
      const container = document.getElementById(elId);
      if (container) {
        const children = container.querySelectorAll('[class*="overflow-y-auto"]');
        if (children[ci]) children[ci].scrollTop = scrollPos[k];
      }
    });
  });
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
              <div class="text-[7px] text-slate-500 font-mono whitespace-pre-wrap break-all max-h-32 overflow-y-auto mt-0.5">${escapeHtml(cContent.substring(0, 10000))}${cContent.length > 10000 ? '<span class="text-slate-600"> ...</span>' : ''}</div>
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
  const active = $('dbgview-events');
  if (active && active.offsetParent !== null) renderRawEvents();
}

function renderRawEvents() {
  const el = $('dbgview-events');
  if (!el) return;

  // Save expanded state + scroll positions
  const expanded = new Set();
  const scrollPos = {};
  el.querySelectorAll('[id^="evt-"]').forEach(d => {
    const idx = parseInt(d.id.replace('evt-', ''), 10);
    if (!isNaN(idx)) {
      if (!d.classList.contains('hidden')) expanded.add(idx);
      d.querySelectorAll('[class*="overflow-y-auto"]').forEach((c, ci) => {
        scrollPos[`evt-${idx}-${ci}`] = c.scrollTop;
      });
    }
  });

  if (debugEventLog.length === 0) {
    el.innerHTML = '<div class="text-[10px] text-slate-600 italic">No events yet.</div>';
    return;
  }

  let html = '';
  for (let i = debugEventLog.length - 1; i >= 0; i--) {
    const entry = debugEventLog[i];
    const evtType = entry.data.type || 'unknown';
    const isExpanded = expanded.has(i) ? '' : 'hidden';

    if (evtType === 'chat_token' || evtType === 'chat_stream_diag' || evtType === 'chat_reasoning_token' || evtType === 'ping') continue;
    if (evtType === 'raw_lm_request') {
      const msgCount = (entry.data.messages || []).length;
      const model = entry.data.model || '?';
      html += `<div class="border border-indigo-500/15 rounded-md px-2 py-1.5 mb-1 bg-indigo-500/5">
        <div class="text-[8px] font-mono leading-relaxed cursor-pointer hover:opacity-80" onclick="document.getElementById('evt-${i}').classList.toggle('hidden')">
          <span class="text-slate-600">${entry.time}</span>
          <span class="text-indigo-400 font-bold">LM REQUEST</span>
          <span class="text-slate-500">${model}</span>
          <span class="text-slate-600">${msgCount} msgs</span>
        </div>
        <div id="evt-${i}" class="${isExpanded} mt-1 pl-2 border-l border-indigo-500/20">
          <div class="text-[7px] text-slate-500 font-mono whitespace-pre-wrap break-all max-h-64 overflow-y-auto">${(escapeHtml(JSON.stringify(entry.data.messages, null, 2)) || '(empty)').replace(/\\n/g, '\n')}</div>
        </div>
      </div>`;
    } else if (evtType === 'raw_lm_response') {
      const content = entry.data.content || '';
      const diag = entry.data.diagnostics || {};
      const tokenInfo = diag.total_output_tokens ? `${diag.total_output_tokens} tokens` : '';
      html += `<div class="border border-emerald-500/15 rounded-md px-2 py-1.5 mb-1 bg-emerald-500/5">
        <div class="text-[8px] font-mono leading-relaxed cursor-pointer hover:opacity-80" onclick="document.getElementById('evt-${i}').classList.toggle('hidden')">
          <span class="text-slate-600">${entry.time}</span>
          <span class="text-emerald-400 font-bold">LM RESPONSE</span>
          <span class="text-slate-500">${tokenInfo}</span>
        </div>
        <div id="evt-${i}" class="${isExpanded} mt-1 pl-2 border-l border-emerald-500/20">
          <div class="text-[7px] text-slate-500 font-mono whitespace-pre-wrap break-all max-h-64 overflow-y-auto">${escapeHtml(content) || '(empty)'}</div>
        </div>
      </div>`;
    } else {
      const typeColor = evtType === 'chat_done' ? 'text-emerald-400' : evtType === 'reasoning_done' ? 'text-amber-400' : evtType === 'tool_use' ? 'text-rose-400' : 'text-slate-400';
      html += `<div class="text-[8px] font-mono leading-relaxed border-b border-white/5 pb-0.5 mb-0.5 cursor-pointer hover:bg-white/5" onclick="document.getElementById('evt-${i}').classList.toggle('hidden')">
        <span class="text-slate-600">${entry.time}</span>
        <span class="${typeColor}">${evtType}</span>
        <div id="evt-${i}" class="${isExpanded} mt-0.5 pl-2 border-l border-white/5">
          <div class="text-[7px] text-slate-500 font-mono whitespace-pre-wrap break-all max-h-48 overflow-y-auto">${escapeHtml(JSON.stringify(entry.data, null, 2))}</div>
        </div>
      </div>`;
    }
  }
  el.innerHTML = html;

  // Restore scroll positions
  requestAnimationFrame(() => {
    Object.keys(scrollPos).forEach(k => {
      const parts = k.split('-');
      const elId = `${parts[0]}-${parts[1]}`;
      const ci = parseInt(parts[2], 10);
      const container = document.getElementById(elId);
      if (container) {
        const children = container.querySelectorAll('[class*="overflow-y-auto"]');
        if (children[ci]) children[ci].scrollTop = scrollPos[k];
      }
    });
  });
}
