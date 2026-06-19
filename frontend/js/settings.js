"use strict";

/* ── Settings / Self-Dev / Approval Mode ──────────────────────── */

/* ── Approval Mode ────────────────────────────────────────────── */

function updateApprovalBadge(mode) {
  const badge = $('approval-mode-badge');
  const labels = {
    'WAIT_FOR_USER': {text:'WAIT', cls:'badge cursor-pointer bg-amber-500/10 text-amber-400 border-amber-500/30'},
    'CHECK_WITH_OVERSEER': {text:'OVERSEER', cls:'badge cursor-pointer bg-indigo-500/10 text-indigo-400 border-indigo-500/30'},
    'AUTO_APPROVE': {text:'AUTO', cls:'badge cursor-pointer bg-emerald-500/10 text-emerald-400 border-emerald-500/30'}
  };
  const info = labels[mode] || labels['WAIT_FOR_USER'];
  if (badge) { badge.textContent = info.text; badge.className = info.cls; }
  const display = $('approval-mode-display');
  if (display) display.textContent = mode;
}

async function loadApprovalMode() {
  try {
    const r = await fetch('/api/session');
    const d = await r.json();
    if (d.approval_mode) updateApprovalBadge(d.approval_mode);
  } catch(_) {}
}

/* ── Approval Mode Cycling ────────────────────────────────────── */

function setupApprovalCycle() {
  const badge = $('approval-mode-badge');
  if (!badge) return;
  badge.onclick = async () => {
    const currentLabel = badge.textContent;
    const modes = ['WAIT', 'OVERSEER', 'AUTO'];
    const apiModes = ['WAIT_FOR_USER', 'CHECK_WITH_OVERSEER', 'AUTO_APPROVE'];
    const idx = modes.indexOf(currentLabel);
    const next = apiModes[(idx + 1) % apiModes.length];
    try {
      const r = await fetch('/api/session/approval-mode', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({mode:next})
      });
      const d = await r.json();
      updateApprovalBadge(d.approval_mode);
    } catch(_) {}
  };
}

/* ── Self-Dev Controls ────────────────────────────────────────── */

async function sdInit() {
  const output = $('sd-output');
  try {
    const r = await fetch('/api/self-dev/init', {method:'POST'});
    const d = await r.json();
    if (output) output.textContent = d.message || JSON.stringify(d);
  } catch(e) { if (output) output.textContent = `Error: ${e.message}`; }
}

async function sdTest() {
  const output = $('sd-output');
  if (output) output.textContent = 'Running tests...';
  try {
    const r = await fetch('/api/self-dev/test', {method:'POST'});
    const d = await r.json();
    if (d.results) {
      let txt = `Status: ${d.results.status}\nTests: ${d.results.tests_run} | +${d.results.passed}/-${d.results.failed}`;
      if (d.results.errors?.length) txt += `\nErrors: ${d.results.errors.join('\n')}`;
      if (output) output.textContent = txt;
    } else if (output) output.textContent = JSON.stringify(d);
  } catch(e) { if (output) output.textContent = `Error: ${e.message}`; }
}

async function sdDeploy() {
  const output = $('sd-output');
  try {
    const r = await fetch('/api/self-dev/deploy', {method:'POST'});
    const d = await r.json();
    if (output) output.textContent = d.message || JSON.stringify(d);
  } catch(e) { if (output) output.textContent = `Error: ${e.message}`; }
}

async function sdStatus() {
  const output = $('sd-output');
  try {
    const r = await fetch('/api/self-dev/status');
    const d = await r.json();
    if (output) output.textContent = JSON.stringify(d, null, 2);
  } catch(e) { if (output) output.textContent = `Error: ${e.message}`; }
}

/* ── Notes ────────────────────────────────────────────────────── */

let notesTimer = null;

async function loadNotes() {
  try {
    const r = await fetch('/api/notes');
    const d = await r.json();
    const editor = $('notes-editor');
    if (editor) editor.value = d.content;
  } catch(_) {}
}

function debounceAutoSaveNotes() {
  const status = $('notes-status');
  if (status) status.textContent = 'unsaved changes...';
  clearTimeout(notesTimer);
  notesTimer = setTimeout(() => saveNotes(true), 800);
}

async function saveNotes(silent) {
  const editor = $('notes-editor');
  const status = $('notes-status');
  if (!editor) return;
  try {
    await fetch('/api/notes', {
      method:'PUT', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({message: editor.value})
    });
    if (!silent) showToast('notes saved');
    if (status) status.textContent = 'saved';
    setTimeout(() => { if (status && status.textContent === 'saved') status.textContent = ''; }, 2000);
  } catch(_) {}
}

/* ── LM Status polling ────────────────────────────────────────── */

async function checkLmStatus() {
  try {
    const r = await fetch('/api/lm/status');
    const d = await r.json();
    const badge = $('lm-badge');
    if (!badge) return;
    if (d.status === 'connected') {
      badge.textContent = `LM ${d.model || ''}`;
      badge.className = 'badge bg-emerald-500/10 text-emerald-400 border-emerald-500/30';
    } else {
      badge.textContent = 'LM \u25cb';
      badge.className = 'badge bg-slate-800 text-slate-500 border border-white/5';
    }
  } catch(_) {}
}

/* ── Sleep Context Generation ─────────────────────────────────── */

function setupSleepControls() {
  const genBtn = $('sleep-gen-btn');
  const flowBtn = $('sleep-flow-btn');
  const from = $('sleep-from');
  const to = $('sleep-to');
  const guidance = $('sleep-guidance');
  const output = $('sleep-output');

  if (genBtn) genBtn.onclick = async () => {
    if (!from || !to || !from.value || !to.value) {
      if (output) output.textContent = 'Please set both From and To times.';
      return;
    }
    const fromTs = parseUtcDatetime(from.value);
    const toTs = parseUtcDatetime(to.value);
    if (isNaN(fromTs) || isNaN(toTs)) {
      if (output) output.textContent = 'Invalid time format. Use YYYY-MM-DD HH:MM (UTC).';
      return;
    }
    if (output) output.textContent = 'Generating context...';
    try {
      const r = await fetch('/api/sleep-context', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({start_time: fromTs, end_time: toTs})
      });
      const d = await r.json();
      if (output) output.textContent = d.context || 'No context generated.';
    } catch(e) { if (output) output.textContent = `Error: ${e.message}`; }
  };

  if (flowBtn) flowBtn.onclick = async () => {
    if (!from || !to || !from.value || !to.value) {
      if (output) output.textContent = 'Please set both From and To times.';
      return;
    }
    const fromTs = parseUtcDatetime(from.value);
    const toTs = parseUtcDatetime(to.value);
    if (isNaN(fromTs) || isNaN(toTs)) {
      if (output) output.textContent = 'Invalid time format.';
      return;
    }
    switchView('console');
    const conv = $('conversation');
    if (conv) conv.innerHTML = `<div id="welcome-msg" class="text-slate-600 italic text-[11px] text-center py-8">ready.</div>`;
    const input = $('msg-input');
    if (input) {
      input.placeholder = 'Optional guidance \u2014 press respond to start sleep flow...';
      input.value = guidance ? guidance.value : '';
    }
    autoResizeTextarea();
    sleepMode = true;
    addMessage('sleep mode ready \u2014 enter optional guidance and press respond', 'amber-400');
  };
}
