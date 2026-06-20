"use strict";

/* ── View Switching ───────────────────────────────────────────── */

function switchView(view) {
  document.querySelectorAll('[id^="panel-"]').forEach(p => p.classList.add('hidden'));
  const panel = $(`panel-${view}`);
  if (panel) panel.classList.remove('hidden');
  document.querySelectorAll('.nav-tab').forEach(t => {
    const isActive = t.dataset.view === view;
    t.className = isActive
      ? 'nav-tab px-3 py-1.5 text-[10px] font-bold uppercase tracking-widest rounded-md bg-indigo-500/10 text-indigo-400 border border-indigo-500/20'
      : 'nav-tab px-3 py-1.5 text-[10px] font-bold uppercase tracking-widest rounded-md text-slate-500 hover:text-slate-300 transition';
  });
  if (view === 'notes') { loadNotes(); initNotesView(); switchNotesView('notes'); }
  if (view === 'memory') { loadMemoryGraph(); switchMemView('nodes'); }
  if (view === 'models') loadModelList();
  if (view === 'debug') initDebugView();
}

/* ── Initialize everything ────────────────────────────────────── */

(async () => {
  await initSession();
  connectWS();
  switchView('console');
  loadNotes();
  fetchTodos();
  loadApprovalMode();
  loadSleepTimerange();
  checkLmStatus();
  setInterval(checkLmStatus, 10000);
  initSystemMonitor();
  loadThinkingLevel();
  updateReminderTimeMin();

  // Thinking level change handler
  const tlSelect = $('thinking-level');
  if (tlSelect) {
    tlSelect.addEventListener('change', async () => {
      try {
        await fetch('/api/chat/thinking-level', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ level: tlSelect.value }),
        });
      } catch(_) {}
    });
  }
})();
