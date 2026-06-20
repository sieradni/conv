"use strict";

let _swTick = null;
let _swRunning = false;
let _swElapsed = 0;    // base elapsed (server's accumulated time)
let _swStarted = 0;    // server timestamp when started (epoch seconds)

function initStopwatchView() {
  document.querySelectorAll('.notes-subtab').forEach(t =>
    t.addEventListener('click', () => switchNotesView(t.dataset.notesview))
  );
}

async function loadStopwatch() {
  try {
    const r = await fetch('/api/stopwatch');
    if (!r.ok) return;
    const s = await r.json();
    applyStopwatchState(s);
  } catch (_) {}
}

function applyStopwatchState(s) {
  _swRunning = s.running;
  _swElapsed = s.elapsed;
  _swStarted = s.started_at || 0;
  renderStopwatch();
  if (s.running) startTick(); else stopTick();
}

function currentElapsed() {
  return _swRunning ? _swElapsed + (Date.now() / 1000 - _swStarted) : _swElapsed;
}

function renderStopwatch() {
  const el = currentElapsed();
  const display = $('stopwatch-display');
  const startBtn = $('stopwatch-start');
  const stopBtn = $('stopwatch-stop');
  if (!display) return;

  display.textContent = fmtStopwatch(el);
  display.className = _swRunning
    ? 'text-3xl font-mono font-bold text-emerald-400 tabular-nums'
    : 'text-3xl font-mono font-bold text-slate-200 tabular-nums';

  if (startBtn) startBtn.disabled = _swRunning;
  if (stopBtn) stopBtn.disabled = !_swRunning;
}

function fmtStopwatch(seconds) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  const ms = Math.floor((s - Math.floor(s)) * 10);
  const ss = Math.floor(s);
  if (h > 0) {
    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(ss).padStart(2, '0')}.${ms}`;
  }
  return `${String(m).padStart(2, '0')}:${String(ss).padStart(2, '0')}.${ms}`;
}

async function startStopwatch() {
  try {
    const r = await fetch('/api/stopwatch/start', { method: 'POST' });
    if (!r.ok) return;
    applyStopwatchState(await r.json());
  } catch (_) {}
}

async function stopStopwatch() {
  try {
    const r = await fetch('/api/stopwatch/stop', { method: 'POST' });
    if (!r.ok) return;
    applyStopwatchState(await r.json());
  } catch (_) {}
}

async function resetStopwatch() {
  stopTick();
  try {
    const r = await fetch('/api/stopwatch/reset', { method: 'POST' });
    if (!r.ok) return;
    applyStopwatchState(await r.json());
  } catch (_) {}
}

function startTick() {
  stopTick();
  _swTick = setInterval(renderStopwatch, 100);
}

function stopTick() {
  if (_swTick) { clearInterval(_swTick); _swTick = null; }
}
