"use strict";

/* ── Chat state ────────────────────────────────────────────────── */

let isRunning = false;
let sleepMode = false;
let currentGoal = '';
let genStartTime = 0;
let msgCounter = 0;
let chatResponseId = null;
let chatResponseBuffer = '';
let thinkingResponseId = null;
let skipNextTaskMsg = false;

const conversation = $('conversation');
const approvalBanner = $('approval-banner');

/* ── Generating Indicator ─────────────────────────────────────── */

function showGenerating(label) {
  genStartTime = Date.now();
  const el = $('generating-indicator');
  const status = $('gen-status');
  const timing = $('gen-timing');
  if (status) status.textContent = label || 'generating...';
  if (el) el.classList.remove('hidden');
  if (timing) timing.textContent = '';
  const stop = $('stop-btn');
  const pause = $('pause-btn');
  if (stop) stop.disabled = false;
  if (pause) { pause.disabled = false; pause.textContent = 'pause'; }
  scrollChat();
}

function updateGenerating(label, diag) {
  const elapsed = ((Date.now() - genStartTime) / 1000).toFixed(1);
  const status = $('gen-status');
  const timing = $('gen-timing');
  if (status) status.textContent = label || 'generating...';
  if (timing) timing.textContent = diag && diag.tokens_per_second
    ? `${elapsed}s | ${diag.tokens_per_second.toFixed(1)} t/s | ${diag.token_count || 0} tok`
    : `${elapsed}s`;
}

function hideGenerating(diag) {
  const el = $('generating-indicator');
  const timing = $('gen-timing');
  if (el) el.classList.add('hidden');
  if (timing && diag) {
    timing.textContent = formatDiag(diag);
    setTimeout(() => { if (el && el.classList.contains('hidden')) timing.textContent = ''; }, 3000);
  }
  const stop = $('stop-btn');
  const pause = $('pause-btn');
  if (stop) stop.disabled = true;
  if (pause) { pause.disabled = true; pause.textContent = 'pause'; }
}

/* ── Dividers ──────────────────────────────────────────────────── */

function divider(color = 'white') {
  const d = document.createElement('div');
  d.className = `h-px bg-${color}/5 my-1 slide-up`;
  return d;
}

/* ── Message rendering ────────────────────────────────────────── */

function removeWelcome() {
  const w = $('welcome-msg');
  if (w) w.remove();
}

function addMessage(text, color = 'slate-400') {
  msgCounter++;
  const id = msgId('msg');
  const d = document.createElement('div');
  d.id = id;
  d.dataset.msg = JSON.stringify({text, color, step_number: msgCounter});
  d.innerHTML = `<div class="h-px bg-white/5 my-1"></div>
<div class="msg-text">
  <span class="text-${color} text-[11px] leading-relaxed">${text}</span>
</div>
<div class="flex gap-1.5 items-center mt-1 pt-1 border-t border-white/5">
  <button onclick="copyMsg('${id}')" class="text-[9px] text-slate-600 hover:text-slate-400 transition px-1.5 py-0.5 bg-black/30 rounded" title="Copy">copy</button>
  <button onclick="editMsg('${id}')" class="text-[9px] text-slate-600 hover:text-slate-400 transition px-1.5 py-0.5 bg-black/30 rounded" title="Edit">edit</button>
  <button onclick="deleteMsg('${id}')" class="text-[9px] text-slate-600 hover:text-rose-400 transition px-1.5 py-0.5 bg-black/30 rounded" title="Delete">delete</button>
  <button onclick="rerunMsg('${id}')" class="text-[9px] text-slate-600 hover:text-slate-400 transition px-1.5 py-0.5 bg-black/30 rounded" title="Rerun">rerun</button>
  <button onclick="branchHere('${id}')" class="text-[9px] text-slate-600 hover:text-indigo-400 transition px-1.5 py-0.5 bg-black/30 rounded" title="Branch">branch</button>
</div>`;
  conversation.appendChild(d);
  removeWelcome();
  scrollChat();
  return id;
}

function addResponseMsg(text, color = 'emerald-400', diag) {
  msgCounter++;
  const id = msgId('msg');
  const d = document.createElement('div');
  d.id = id;
  d.dataset.msg = JSON.stringify({text, color, step_number: msgCounter});
  let html = `<div class="h-px bg-white/5 my-1"></div>
<div class="msg-text">
  <div class="msg-content markdown text-${color} text-[11px] leading-relaxed">${renderMarkdown(text)}</div>
</div>`;
  if (diag) {
    html += `<div class="flex gap-2 mt-1 pt-1 border-t border-white/5 text-[8px] font-mono text-slate-600">${formatDiag(diag)}</div>`;
  }
  html += `<div class="flex gap-1.5 items-center mt-1 pt-1 border-t border-white/5">
  <button onclick="copyMsg('${id}')" class="text-[9px] text-slate-600 hover:text-slate-400 transition px-1.5 py-0.5 bg-black/30 rounded">copy</button>
  <button onclick="editMsg('${id}')" class="text-[9px] text-slate-600 hover:text-slate-400 transition px-1.5 py-0.5 bg-black/30 rounded">edit</button>
  <button onclick="deleteMsg('${id}')" class="text-[9px] text-slate-600 hover:text-rose-400 transition px-1.5 py-0.5 bg-black/30 rounded">delete</button>
  <button onclick="rerunMsg('${id}')" class="text-[9px] text-slate-600 hover:text-slate-400 transition px-1.5 py-0.5 bg-black/30 rounded">rerun</button>
  <button onclick="branchHere('${id}')" class="text-[9px] text-slate-600 hover:text-indigo-400 transition px-1.5 py-0.5 bg-black/30 rounded">branch</button>
</div>`;
  d.innerHTML = html;
  conversation.appendChild(d);
  removeWelcome();
  scrollChat();
  return id;
}

function addMsgWithCursor(text, color = 'emerald-400') {
  msgCounter++;
  const id = msgId('msg');
  const d = document.createElement('div');
  d.id = id;
  d.dataset.msg = JSON.stringify({text, color, step_number: msgCounter});
  d.innerHTML = `<div class="h-px bg-white/5 my-1"></div>
<div class="msg-text">
  <span class="msg-content text-${color} text-[11px] leading-relaxed">${text}</span><span class="msg-cursor text-${color} text-[11px] font-bold animate-pulse">...</span>
</div>`;
  conversation.appendChild(d);
  removeWelcome();
  scrollChat();
  return id;
}

function color2border(c) {
  if (c === 'indigo-400') return 'indigo';
  if (c === 'rose-400') return 'rose';
  if (c === 'emerald-400') return 'emerald';
  if (c === 'amber-400') return 'amber';
  return 'slate';
}

/* ── Message Actions ──────────────────────────────────────────── */

function copyMsg(id) {
  const el = $(id); if (!el) return;
  const msg = JSON.parse(el.dataset.msg || '{}');
  navigator.clipboard.writeText(msg.text).catch(()=>{});
  showToast('copied');
}

function editMsg(id) {
  const el = $(id); if (!el) return;
  const msg = JSON.parse(el.dataset.msg || '{}');
  let text = msg.text;
  const prefixes = ['launching: ', 'respond: ', 'task: ', 'talk: ', 'asked: ', 'resumed: ', 'you: ', 'error: '];
  for (const p of prefixes) {
    if (text.startsWith(p)) { text = text.slice(p.length); break; }
  }
  if (text.startsWith('"') && text.endsWith('"')) text = text.slice(1, -1);

  const container = el.querySelector('.msg-text');
  if (!container) return;

  const input = document.createElement('input');
  input.type = 'text';
  input.value = text;
  input.className = 'bg-black/60 border border-indigo-500/50 rounded px-2 py-1 text-[11px] text-slate-200 w-full focus:outline-none';
  container.innerHTML = '';
  container.appendChild(input);
  input.focus();
  input.select();

  const save = () => {
    const newText = input.value.trim();
    const displayText = newText || text;
    if (newText && newText !== text) {
      msg.text = displayText;
      el.dataset.msg = JSON.stringify(msg);
    }
    const span = document.createElement('span');
    span.className = `text-${msg.color} text-[11px] leading-relaxed`;
    span.textContent = displayText;
    container.innerHTML = '';
    container.appendChild(span);
  };

  input.addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); input.blur(); }
    if (e.key === 'Escape') { save(); }
  });
  input.addEventListener('blur', save);
}

async function deleteMsg(id) {
  const el = $(id); if (!el) return;

  // Also remove from backend history
  const allMsgs = conversation.querySelectorAll('[data-msg]');
  let idx = 0;
  for (const m of allMsgs) {
    if (m.id === id) break;
    idx++;
  }
  fetch(`/api/session/message?index=${idx}`, { method:'DELETE' }).catch(()=>{});

  // Remove preceding thinking block if present
  const prev = el.previousElementSibling;
  if (prev && prev.id && prev.id.startsWith('thinking-')) {
    prev.remove();
    if (thinkingResponseId === prev.id) thinkingResponseId = null;
  }
  el.innerHTML = `<div class="h-px bg-white/5 my-1"></div>
<div><span class="text-[11px] text-slate-600 italic">deleted</span></div>`;
}

async function rerunMsg(id) {
  const el = $(id); if (!el) return;
  const msg = JSON.parse(el.dataset.msg || '{}');
  let text = msg.text || '';

  // Find the "you:" element to branch from (target if it's a user msg, else preceding)
  let youEl;
  if (text.startsWith('you: ')) {
    youEl = el;
  } else {
    let prev = el.previousElementSibling;
    while (prev) {
      const prevMsg = JSON.parse(prev.dataset.msg || '{}');
      if (prevMsg.text && prevMsg.text.startsWith('you: ')) {
        youEl = prev;
        break;
      }
      prev = prev.previousElementSibling;
    }
    if (!youEl) { showToast('no user message found'); return; }
  }

  const userText = JSON.parse(youEl.dataset.msg || '{}').text.slice(5);

  // Count [data-msg] elements BEFORE the "you:" element
  const allMsgs = conversation.querySelectorAll('[data-msg]');
  let keep = 0;
  for (const m of allMsgs) {
    if (m.id === youEl.id) break;
    keep++;
  }

  // Remove the "you:" element and everything after it
  let toRemove = [];
  let cur = youEl;
  while (cur) {
    toRemove.push(cur);
    cur = cur.nextElementSibling;
  }
  for (const r of toRemove) r.remove();

  // Truncate backend history BEFORE the user message
  try {
    await fetch('/api/session/truncate', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({keep}),
    });
  } catch(_) { return; }

  // Add the user message back to DOM (same as respond-btn.onclick)
  addMessage(`you: ${userText}`, 'indigo-400');

  // Trigger agent with original user message (will be saved to history by backend)
  fetch('/api/chat', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({message: userText}),
  }).catch(()=>{});
}

async function branchHere(id) {
  const el = $(id); if (!el) return;

  // Count [data-msg] up to and including this one
  const allMsgs = conversation.querySelectorAll('[data-msg]');
  let keep = 0;
  for (const m of allMsgs) {
    keep++;
    if (m.id === id) break;
  }

  // Remove DOM after this message
  let next = el.nextElementSibling;
  while (next) {
    const cur = next;
    next = next.nextElementSibling;
    cur.remove();
  }

  // Truncate backend history
  try {
    await fetch('/api/session/truncate', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({keep}),
    });
  } catch(_) {}

  showToast('branched');
}

/* ── Tool Cards ────────────────────────────────────────────────── */

function addToolCard(msg) {
  const tid = 'chtool-' + Date.now() + '-' + Math.random().toString(36).slice(2,6);
  const toolArgs = msg.tool_args || {};
  const argsStr = Object.keys(toolArgs).length
    ? Object.entries(toolArgs).map(([k,v]) => `${k}: ${typeof v === 'string' ? v : JSON.stringify(v)}`).join('\n')
    : '';
  const diag = msg.diagnostics || {};
  const diagStr = formatDiag(diag);

  const d = document.createElement('div');
  d.id = tid;
  d.innerHTML = `<div class="h-px bg-indigo-500/10 my-1"></div>
<div class="flex items-center gap-1.5 mb-1">
  <span class="text-[9px] text-indigo-400 font-medium">&#9881; ${escapeHtml(msg.tool_name)}</span>
  ${diagStr ? `<span class="text-[8px] text-slate-600 font-mono ml-auto">${diagStr}</span>` : ''}
  ${argsStr ? `<button id="${tid}-tbtn" onclick="toggleToolArgs('${tid}')" class="text-[8px] text-slate-600 hover:text-slate-400 ml-1">hide</button>` : ''}
</div>
<div id="${tid}-a" class="${argsStr ? '' : 'hidden'}"><pre class="text-[9px] text-slate-500 bg-black/30 border border-white/5 rounded p-1 mono overflow-x-auto max-w-full whitespace-pre-wrap break-all" style="max-height:200px">${escapeHtml(argsStr)}</pre></div>
<div id="${tid}-r" class="text-[10px] text-slate-500 leading-relaxed"></div>`;
  conversation.appendChild(d);
  removeWelcome();
  scrollChat();
}

function addToolResult(msg) {
  const tools = conversation.querySelectorAll('[id^="chtool-"]');
  if (tools.length > 0) {
    const last = tools[tools.length - 1];
    const rid = last.id + '-r';
    let rEl = $(rid) || last.querySelector('[id$="-r"]');
    if (rEl) {
      rEl.innerHTML = '';
      const obs = msg.observation || '';
      if (obs) {
        const pre = document.createElement('pre');
        pre.className = 'text-[10px] text-slate-200 leading-relaxed border-t border-white/5 pt-1 mt-1 overflow-x-auto max-w-full whitespace-pre-wrap break-all mono';
        pre.textContent = obs;
        rEl.appendChild(pre);
      }
    } else if (msg.observation) {
      addResponseMsg(msg.observation, 'slate-300');
    }
  } else if (msg.observation) {
    addResponseMsg(msg.observation, 'slate-300');
  }
}

function toggleToolArgs(tid) {
  const el = $(tid + '-a');
  const btn = $(tid + '-tbtn');
  if (!el) return;
  el.classList.toggle('hidden');
  if (btn) btn.textContent = el.classList.contains('hidden') ? 'show' : 'hide';
}

/* ── Overseer Review ───────────────────────────────────────────── */

function addOverseerReview(msg) {
  const approved = msg.approved;
  const status = msg.status || (approved ? 'APPROVED' : 'REJECTED');
  const color = approved ? 'emerald' : 'rose';
  const id = 'ov-' + Date.now();

  const d = document.createElement('div');
  d.innerHTML = `<div class="h-px bg-${color}-500/10 my-1"></div>
<div class="flex items-center justify-between mb-1">
  <span class="text-[9px] font-bold text-${color}-400 uppercase tracking-wider">&#128220; overseer: ${status}</span>
  <div class="flex gap-1">
    <button onclick="toggle('${id}')" class="text-[9px] text-slate-600 hover:text-slate-400 transition">${msg.feedback ? 'details' : ''}</button>
    ${!approved ? `<button onclick="overrideOverseer()" class="text-[9px] text-indigo-400 hover:text-indigo-300 transition">override</button>` : ''}
  </div>
</div>
<div class="text-[10px] text-slate-400 leading-relaxed">${escapeHtml(msg.reasoning||'')}</div>
<div id="${id}" class="${msg.feedback ? '' : 'hidden'}">
  ${msg.feedback ? `<p class="text-[10px] text-slate-500 mt-1 italic">${escapeHtml(msg.feedback)}</p>` : ''}
</div>`;
  conversation.appendChild(d);
  removeWelcome();
  scrollChat();
}

async function overrideOverseer() {
  const feedback = prompt('Override feedback for the agent:');
  if (feedback === null) return;
  try {
    await fetch('/api/approve', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({approved:true, feedback:`[OVERRIDE] ${feedback}`}) });
    addMessage(`overseer overridden: ${feedback}`, 'indigo-400');
  } catch(_) {}
}

/* ── Approval Banner ───────────────────────────────────────────── */

function showApproval(msg) {
  const isAsk = msg.tool_name === 'ask_user' || msg.type === 'ask_user';
  const title = $('approval-title');
  const thought = $('approval-thought');
  const argsEl = $('approval-args');
  const feedbackInput = $('feedback-input');
  const approveBtn = $('approve-btn');
  const rejectBtn = $('reject-btn');

  if (title) title.textContent = isAsk ? 'agent asks:' : 'approval required';
  if (thought) thought.textContent = msg.thought || msg.tool_args?.question || '';
  if (argsEl) {
    if (msg.tool_args && Object.keys(msg.tool_args).length > 0 && !isAsk) {
      argsEl.textContent = JSON.stringify(msg.tool_args, null, 2);
      argsEl.classList.remove('hidden');
    } else {
      argsEl.classList.add('hidden');
    }
  }
  if (feedbackInput) {
    feedbackInput.value = '';
    feedbackInput.placeholder = isAsk ? 'your answer...' : 'feedback (optional)';
  }
  if (approveBtn) approveBtn.textContent = isAsk ? 'answer' : 'approve';
  if (rejectBtn) rejectBtn.textContent = isAsk ? 'skip' : 'reject';
  if (approvalBanner) approvalBanner.classList.remove('hidden');
  setTimeout(() => { if (feedbackInput) feedbackInput.focus(); }, 100);
}

function hideApproval() { if (approvalBanner) approvalBanner.classList.add('hidden'); }

async function submitApproval(approved) {
  const feedbackInput = $('feedback-input');
  const feedback = feedbackInput ? feedbackInput.value.trim() : '';
  hideApproval();
  try {
    await fetch('/api/approve', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({approved, feedback: feedback || undefined})
    });
  } catch(_) {}
}

/* ── Todo List ─────────────────────────────────────────────────── */

function updatedTaskDisplay() {
  const el = $('current-task-display');
  if (!el) return;
  if (currentGoal) {
    el.innerHTML = `<span class="text-slate-500">task:</span> ${escapeHtml(currentGoal)}`;
    el.classList.remove('hidden');
  } else {
    el.classList.add('hidden');
  }
}

async function fetchTodos() {
  try {
    const r = await fetch('/api/todos');
    const d = await r.json();
    const items = d.todo_items || [];
    const completed = d.completed_items || [];
    const panel = $('todo-panel');
    const list = $('todo-items');
    const count = $('todo-count');
    if (!panel || !list) return;
    if (items.length === 0 && completed.length === 0) {
      panel.classList.add('hidden');
      return;
    }
    panel.classList.remove('hidden');
    if (count) count.textContent = `${items.length} pending \u00b7 ${completed.length} done`;
    list.innerHTML = '';
    items.forEach((item, i) => {
      const li = document.createElement('li');
      li.className = 'text-[10px] text-slate-300 flex items-start gap-1.5';
      li.innerHTML = `<span class="text-indigo-400 shrink-0 mt-0.5">&#8226;</span><span>${escapeHtml(typeof item === 'string' ? item : JSON.stringify(item))}</span>`;
      list.appendChild(li);
    });
    if (completed.length > 0 && items.length > 0) {
      const sep = document.createElement('li');
      sep.className = 'text-[9px] text-slate-600 pt-1';
      sep.textContent = 'completed:';
      list.appendChild(sep);
    }
    completed.forEach(item => {
      const li = document.createElement('li');
      li.className = 'text-[10px] text-slate-500 flex items-start gap-1.5';
      li.innerHTML = `<span class="text-emerald-500 shrink-0 mt-0.5">&#10003;</span><span>${escapeHtml(typeof item === 'string' ? item : JSON.stringify(item))}</span>`;
      list.appendChild(li);
    });
  } catch(_) {}
}

/* ── Thinking block ────────────────────────────────────────────── */

function toggleThinking(id) {
  const body = $(id + '-body');
  const btn = $(id + '-tbtn');
  if (!body) return;
  body.classList.toggle('hidden');
  if (btn) btn.textContent = body.classList.contains('hidden') ? '+' : '\u2212';
}

/* ── Main message handler ──────────────────────────────────────── */

function handleMessage(msg) {
  if (msg.session_id && msg.session_id !== window.sessionId) return;

  switch (msg.type) {

    case 'chat_start':
      if (chatResponseId) break;
      showGenerating('responding...');
      thinkingResponseId = null;
      chatResponseBuffer = '';
      chatResponseId = addMsgWithCursor('', 'emerald-400');
      break;

    case 'reasoning_start':
      break;

    case 'chat_reasoning_token':
      if (!thinkingResponseId) {
        const thinkingId = msgId('thinking');
        const d = document.createElement('div');
        d.id = thinkingId;
        d.innerHTML = `<div class="h-px bg-amber-500/10 my-1"></div>
<div class="flex items-center gap-1.5 mb-1">
  <span class="text-[9px] font-medium text-amber-400">&#9881; thinking</span>
  <button onclick="toggleThinking('${thinkingId}')" class="ml-auto text-[8px] text-slate-600 hover:text-slate-400">\u2212</button>
</div>
<div class="text-[10px] text-amber-300/60 italic leading-relaxed thinking-content thinking-body" id="${thinkingId}-body"></div>`;
        const chatEl = chatResponseId ? $(chatResponseId) : null;
        if (chatEl) {
          conversation.insertBefore(d, chatEl);
        } else {
          conversation.appendChild(d);
        }
        removeWelcome();
        thinkingResponseId = thinkingId;
      }
      {
        const el = $(thinkingResponseId);
        if (el) {
          const contentEl = el.querySelector('.thinking-content');
          if (contentEl) contentEl.textContent += msg.token;
          scrollChat();
        }
      }
      break;

    case 'reasoning_end':
    case 'reasoning_done':
      if (thinkingResponseId && msg.diagnostics) {
        const thinkingEl = $(thinkingResponseId);
        if (thinkingEl) {
          const existingDiag = thinkingEl.querySelector('.thinking-diag');
          if (existingDiag) {
            existingDiag.textContent = formatDiag(msg.diagnostics);
          } else {
            const diagRow = document.createElement('div');
            diagRow.className = 'thinking-diag flex gap-2 mt-1 pt-1 border-t border-amber-500/10 text-[8px] font-mono text-slate-600';
            diagRow.textContent = formatDiag(msg.diagnostics);
            thinkingEl.appendChild(diagRow);
          }
        }
      }
      break;

    case 'chat_token':
      if (chatResponseId) {
        const el = $(chatResponseId);
        if (el) {
          const span = el.querySelector('.msg-text .msg-content');
          const cursor = el.querySelector('.msg-text .msg-cursor');
          if (span) {
            span.classList.add('markdown');
            chatResponseBuffer += msg.token;
            span.innerHTML = renderMarkdown(chatResponseBuffer);
          }
          if (cursor) cursor.textContent = '...';
          scrollChat();
        }
      }
      break;

    case 'chat_stream_diag':
      if (msg.diagnostics) {
        updateGenerating('generating...', msg.diagnostics);
      }
      break;

    case 'chat_tool':
      if (msg.clean_text !== undefined && chatResponseId) {
        const el = $(chatResponseId);
        if (el) {
          const span = el.querySelector('.msg-text .msg-content');
          if (span) {
            span.classList.add('markdown');
            chatResponseBuffer = msg.clean_text;
            span.innerHTML = renderMarkdown(chatResponseBuffer);
          }
        }
      }
      addToolCard(msg);
      break;

    case 'chat_tool_result':
      addToolResult(msg);
      fetchTodos();
      break;

    case 'overseer_review_start':
      updateGenerating('overseer reviewing...');
      break;

    case 'overseer_review_token':
      if (chatResponseId) {
        const el = $(chatResponseId);
        if (el) {
          const span = el.querySelector('.msg-text .msg-content');
          const cursor = el.querySelector('.msg-text .msg-cursor');
          if (span) span.textContent += msg.token;
          if (cursor) cursor.textContent = '...';
          scrollChat();
        }
      }
      break;

    case 'overseer_review':
      hideGenerating(msg.diagnostics);
      addOverseerReview(msg);
      break;

    case 'awaiting_user_approval':
    case 'ask_user':
      hideGenerating();
      showApproval(msg);
      break;

    case 'chat_done':
      hideGenerating(msg.diagnostics);
      if (sleepMode) {
        const wakeBtn = $('wake-btn');
        const msgInput = $('msg-input');
        if (wakeBtn) wakeBtn.classList.add('hidden');
        if (msgInput) msgInput.placeholder = 'Task goal or message for agent...';
        sleepMode = false;
      }
      fetchTodos();
      if (chatResponseId) {
        const el = $(chatResponseId);
        if (el) {
          const msgData = JSON.parse(el.dataset.msg || '{}');
          if (msg.response !== '[Stopped]') {
            chatResponseBuffer = msg.response;
            msgData.text = msg.response;
            el.dataset.msg = JSON.stringify(msgData);
            const contentSpan = el.querySelector('.msg-text .msg-content');
            if (contentSpan) {
              contentSpan.classList.add('markdown');
              contentSpan.innerHTML = renderMarkdown(msg.response);
            }
          }
          const cursor = el.querySelector('.msg-text .msg-cursor');
          if (cursor) cursor.remove();
          // Add diagnostics to completed message
          if (msg.diagnostics) {
            const existingDiag = el.querySelector('.response-diag');
            if (existingDiag) {
              existingDiag.textContent = formatDiag(msg.diagnostics);
            } else {
              const diagRow = document.createElement('div');
              diagRow.className = 'response-diag flex gap-2 mt-1 pt-1 border-t border-white/5 text-[8px] font-mono text-slate-600';
              diagRow.textContent = formatDiag(msg.diagnostics);
              el.appendChild(diagRow);
            }
          }
          // Also update thinking diagnostics with full stats
          if (msg.diagnostics && thinkingResponseId) {
            const thinkingEl = $(thinkingResponseId);
            if (thinkingEl) {
              let diagRow = thinkingEl.querySelector('.thinking-diag');
              if (diagRow) {
                diagRow.textContent = formatDiag(msg.diagnostics);
              } else {
                diagRow = document.createElement('div');
                diagRow.className = 'thinking-diag flex gap-2 mt-1 pt-1 border-t border-amber-500/10 text-[8px] font-mono text-slate-600';
                diagRow.textContent = formatDiag(msg.diagnostics);
                thinkingEl.appendChild(diagRow);
              }
            }
          }
          // Add action buttons to completed streaming message
          if (!el.querySelector('button[onclick*="copyMsg"]')) {
            const btnRow = document.createElement('div');
            btnRow.className = 'flex gap-1.5 items-center mt-1 pt-1 border-t border-white/5';
            btnRow.innerHTML = `
  <button onclick="copyMsg('${chatResponseId}')" class="text-[9px] text-slate-600 hover:text-slate-400 transition px-1.5 py-0.5 bg-black/30 rounded">copy</button>
  <button onclick="editMsg('${chatResponseId}')" class="text-[9px] text-slate-600 hover:text-slate-400 transition px-1.5 py-0.5 bg-black/30 rounded">edit</button>
  <button onclick="deleteMsg('${chatResponseId}')" class="text-[9px] text-slate-600 hover:text-rose-400 transition px-1.5 py-0.5 bg-black/30 rounded">delete</button>
  <button onclick="rerunMsg('${chatResponseId}')" class="text-[9px] text-slate-600 hover:text-slate-400 transition px-1.5 py-0.5 bg-black/30 rounded">rerun</button>
  <button onclick="branchHere('${chatResponseId}')" class="text-[9px] text-slate-600 hover:text-indigo-400 transition px-1.5 py-0.5 bg-black/30 rounded">branch</button>`;
            el.appendChild(btnRow);
          }
        }
        chatResponseId = null;
        chatResponseBuffer = '';
      }
      isRunning = false;
      break;

    case 'chat_paused':
      addMessage('paused — click resume to continue', 'amber-400');
      const pauseBtn = $('pause-btn');
      if (pauseBtn) { pauseBtn.textContent = 'resume'; pauseBtn.disabled = false; }
      break;

    case 'raw_lm_request':
      showGenerating('llm thinking...');
      break;

    case 'task_complete':
      isRunning = false;
      hideGenerating();
      addMessage(`task ${msg.status.toLowerCase()}${msg.summary ? ': ' + msg.summary : ''}`, msg.status === 'COMPLETED' ? 'emerald-400' : 'amber-400');
      fetchTodos();
      break;

    case 'goal_set':
      currentGoal = msg.goal || '';
      addMessage(`goal: ${currentGoal}`, 'indigo-400');
      updatedTaskDisplay();
      break;

    case 'error':
      hideGenerating();
      addMessage(`error: ${msg.message}`, 'rose-400');
      isRunning = false;
      break;

    case 'model_load_start':
    case 'model_load_progress':
    case 'model_load_end':
    case 'prompt_processing_start':
    case 'prompt_processing_end':
      break;

    default:
      break;
  }
}
