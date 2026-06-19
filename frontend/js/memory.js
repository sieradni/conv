"use strict";

/* ── Memory sub-tab switching ─────────────────────────────────── */

function switchMemView(subview) {
  document.querySelectorAll('[id^="memview-"]').forEach(p => p.classList.add('hidden'));
  const panel = $(`memview-${subview}`);
  if (panel) panel.classList.remove('hidden');
  document.querySelectorAll('.mem-subtab').forEach(t => {
    const isActive = t.dataset.memview === subview;
    t.className = isActive
      ? 'mem-subtab px-3 py-1 text-[9px] font-bold uppercase tracking-widest rounded-md bg-indigo-500/10 text-indigo-400 border border-indigo-500/20'
      : 'mem-subtab px-3 py-1 text-[9px] font-bold uppercase tracking-widest rounded-md text-slate-500 hover:text-slate-300 transition';
  });
  if (subview === 'nodes') loadMemoryGraph();
  if (subview === 'sleep') loadSleepTimerange();
}

document.querySelectorAll('.mem-subtab').forEach(t =>
  t.addEventListener('click', () => switchMemView(t.dataset.memview))
);

/* ── Memory Graph ─────────────────────────────────────────────── */

async function loadMemoryGraph() {
  try {
    const r = await fetch('/api/memory');
    const d = await r.json();
    const nodes = d.nodes || [];
    const currentId = d.current_node_id;
    const nodeMap = Object.fromEntries(nodes.map(n => [n.id, n]));
    const count = $('mem-count');
    if (count) count.textContent = `${nodes.length} nodes`;
    const list = $('mem-list');
    if (!list) return;
    let txt = '';
    nodes.forEach(n => {
      const isCurrent = n.id === currentId;
      const marker = isCurrent ? '\u25b6' : ' ';
      const detail = (n.extraneous_detail||'').trim() ? n.extraneous_detail : 'none';
      const linkedNames = (n.linked_ids||[]).map(lid => {
        const ln = nodeMap[lid];
        return ln ? `[${lid}] ${ln.content}` : `[${lid}] (unknown)`;
      }).join(', ') || 'none';
      const tags = [];
      if (n.is_root) tags.push('root');
      if (isCurrent) tags.push('CURRENT');
      const tagStr = tags.length ? ` [${tags.join(', ')}]` : '';
      txt += `${marker} [${n.id}] ${n.content}${tagStr}\n`;
      txt += `  ID: ${n.id}\n`;
      txt += `  Extraneous detail: ${detail}\n`;
      txt += `  Links: ${linkedNames}\n`;
      txt += `  Access: ${n.access_count} | Created: ${fmtUtc(n.created_at)} | Updated: ${fmtUtc(n.updated_at)}\n\n`;
    });
    list.textContent = txt || '[no memories]';
  } catch(_) {}
}

/* ── Sleep Context ────────────────────────────────────────────── */

async function loadSleepTimerange() {
  try {
    const r = await fetch('/api/memory');
    const d = await r.json();
    const nodes = d.nodes || [];
    if (nodes.length === 0) return;
    const times = nodes.map(n => n.created_at);
    const min = Math.min(...times);
    const max = Math.max(...times);
    const from = $('sleep-from');
    const to = $('sleep-to');
    if (from) from.value = fmtUtc(min).slice(0, 16);
    if (to) to.value = fmtUtc(max).slice(0, 16);
  } catch(_) {}
}
