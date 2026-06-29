"use strict";

/* ── Model Management ─────────────────────────────────────────── */

let _modelListData = {};  // keyed by model key

async function loadModelList() {
  const listEl = $('model-list');
  const activeEl = $('model-active');
  if (!listEl) return;

  listEl.innerHTML = '<div class="text-[10px] text-slate-600">Loading models...</div>';

  try {
    const r = await fetch('/api/models');
    const d = await r.json();
    const models = d.models || [];

    // Cache for later lookups
    _modelListData = {};
    for (const m of models) {
      if (m.key) _modelListData[m.key] = m;
    }

    // Show active model
    const activeR = await fetch('/api/models/active');
    const activeD = await activeR.json();
    if (activeEl) {
      activeEl.textContent = activeD.model_instance_id || 'None';
    }

    if (models.length === 0) {
      listEl.innerHTML = '<div class="text-[10px] text-slate-600">No models available. Is LM Studio running?</div>';
      return;
    }

    let html = '';
    for (const m of models) {
      const type = m.type || 'llm';
      const name = m.display_name || m.key || 'Unknown';
      const params = m.params_string || '';
      const quant = m.quantization ? (m.quantization.name || '') : '';
      const isLoaded = m.loaded_instances && m.loaded_instances.length > 0;
      const instanceId = isLoaded ? m.loaded_instances[0].id : null;
      const capVision = m.capabilities?.vision ? 'V' : '';
      const capTools = m.capabilities?.trained_for_tool_use ? 'T' : '';
      const caps = [capVision, capTools].filter(Boolean).join('/');

      html += `<div class="glass rounded-lg p-2.5 ${isLoaded ? 'border-l-2 border-emerald-500/30' : 'border-l-2 border-slate-700/30'}">
        <div class="flex items-center gap-2">
          <span class="text-[9px] font-bold text-${type === 'embedding' ? 'amber' : 'indigo'}-400 uppercase">${type === 'embedding' ? 'emb' : 'llm'}</span>
          <span class="text-[11px] font-medium text-slate-200">${escapeHtml(name)}</span>
          ${isLoaded ? '<span class="badge bg-emerald-500/10 text-emerald-400 border-emerald-500/30 text-[8px]">loaded</span>' : ''}
          ${caps ? `<span class="text-[8px] text-slate-600 font-mono">${caps}</span>` : ''}
        </div>
        <div class="flex gap-3 mt-1 text-[9px] text-slate-500">
          <span>${escapeHtml(m.key || '')}</span>
          ${params ? `<span>${escapeHtml(params)}</span>` : ''}
          ${quant ? `<span>${escapeHtml(quant)}</span>` : ''}
          ${m.format ? `<span>${escapeHtml(m.format)}</span>` : ''}
        </div>
        <div class="flex gap-1.5 mt-1.5">
          ${!isLoaded ? `<button onclick="loadModelClick('${escapeHtml(m.key)}', event)" class="px-2 py-1 bg-indigo-600/20 hover:bg-indigo-600/40 border border-indigo-600/30 rounded text-[8px] font-bold text-indigo-400 transition">load</button>` : ''}
          ${isLoaded && instanceId ? `<button onclick="unloadModelClick('${escapeHtml(instanceId)}', event)" class="px-2 py-1 bg-rose-600/20 hover:bg-rose-600/40 border border-rose-600/30 rounded text-[8px] font-bold text-rose-400 transition">unload</button>` : ''}
        </div>
      </div>`;
    }
    listEl.innerHTML = html;

  } catch(e) {
    listEl.innerHTML = `<div class="text-[10px] text-rose-400">Error loading models: ${e.message}</div>`;
  }
}

async function loadModelClick(modelKey, evt) {
  const modelInfo = _modelListData[modelKey] || {};
  const maxCtx = modelInfo.max_context_length;
  const hint = maxCtx ? ` (max ${maxCtx}, default 8192)` : ' (default 8192)';
  const ctxStr = prompt(`Context length${hint}:`, '8192');
  if (ctxStr === null) return;

  const payload = { model: modelKey };
  if (ctxStr) payload.context_length = parseInt(ctxStr);

  const btn = evt?.target;
  if (btn) { btn.disabled = true; btn.textContent = 'loading...'; }

  try {
    const r = await fetch('/api/models/load', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify(payload)
    });
    const d = await r.json();
    showToast(`Model loaded: ${d.instance_id || modelKey}`);
    loadModelList();
  } catch(e) {
    showToast(`Load failed: ${e.message}`);
    if (btn) { btn.disabled = false; btn.textContent = 'load'; }
  }
}

async function unloadModelClick(instanceId, evt) {
  const btn = evt?.target;
  if (btn) { btn.disabled = true; btn.textContent = 'unloading...'; }

  try {
    const r = await fetch('/api/models/unload', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ instance_id: instanceId })
    });
    if (!r.ok) throw new Error(await r.text());
    const d = await r.json();
    showToast(`Model unloaded: ${instanceId}`);
    loadModelList();
  } catch(e) {
    showToast(`Unload failed: ${e.message}`);
    if (btn) { btn.disabled = false; btn.textContent = 'unload'; }
  }
}
