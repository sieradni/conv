"use strict";

/* ── DOM shortcuts ─────────────────────────────────────────────── */

const $ = id => document.getElementById(id);

/* ── Markdown rendering ────────────────────────────────────────── */

function renderMarkdown(text) {
  if (!text) return '';
  if (typeof katex !== 'undefined') {
    const codeBlocks = [];
    text = text.replace(/(```[\s\S]*?```|`[^`]+`)/g, m => { codeBlocks.push(m); return `\x00CODE${codeBlocks.length-1}\x00`; });
    text = text.replace(/\$\$(.+?)\$\$/gs, (_, eq) => {
      try { return katex.renderToString(eq.trim(), { displayMode:true, throwOnError:false }); }
      catch(e) { return `[LaTeX error]`; }
    });
    text = text.replace(/\$(.+?)\$/g, (_, eq) => {
      try { return katex.renderToString(eq.trim(), { displayMode:false, throwOnError:false }); }
      catch(e) { return `$${eq}$`; }
    });
    text = text.replace(/\x00CODE(\d+)\x00/g, (_, n) => codeBlocks[parseInt(n)] || '');
  }
  const html = marked.parse(text, { breaks:true, gfm:true });
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS:['p','br','strong','em','code','pre','ul','ol','li','a','h1','h2','h3','h4','h5','h6','blockquote','hr','span','div','table','thead','tbody','tr','th','td','del','ins','sub','sup'],
    ALLOWED_ATTR:['href','target','class','id'],
    ADD_TAGS:['math','semantics','annotation','mrow','mi','mn','mo','msup','msub','mfrac','msqrt','mover','munder','mtext','annotation-xml'],
    ADD_ATTR:['xmlns','encoding']
  });
}

/* ── Escaping ──────────────────────────────────────────────────── */

function escapeHtml(s) {
  if (!s) return '';
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

/* ── Toast notifications ──────────────────────────────────────── */

function showToast(msg, parent) {
  const el = document.createElement('div');
  el.className = 'text-[10px] text-slate-500 slide-up';
  el.textContent = msg;
  (parent || conversation).appendChild(el);
  scrollChat();
  setTimeout(() => el.remove(), 2000);
}

/* ── Timestamp formatter ───────────────────────────────────────── */

function fmtUtc(ts) {
  const d = new Date(ts * 1000);
  return d.getUTCFullYear() + '-' +
    String(d.getUTCMonth()+1).padStart(2,'0') + '-' +
    String(d.getUTCDate()).padStart(2,'0') + ' ' +
    String(d.getUTCHours()).padStart(2,'0') + ':' +
    String(d.getUTCMinutes()).padStart(2,'0') + ':' +
    String(d.getUTCSeconds()).padStart(2,'0') + ' UTC';
}

function parseUtcDatetime(str) {
  const m = str.match(/^(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2})$/);
  if (!m) return NaN;
  return Date.UTC(+m[1], +m[2]-1, +m[3], +m[4], +m[5]) / 1000;
}

/* ── Toggle visibility ─────────────────────────────────────────── */

function toggle(elId) {
  const el = $(elId);
  if (!el) return;
  el.classList.toggle('hidden');
}

/* ── Chat scroll ───────────────────────────────────────────────── */

function scrollChat() {
  const conversation = $('conversation');
  if (!conversation) return;
  const threshold = 60;
  const isNearBottom = conversation.scrollHeight - conversation.scrollTop - conversation.clientHeight < threshold;
  if (isNearBottom) conversation.scrollTop = conversation.scrollHeight;
}

/* ── Format diagnostics string ─────────────────────────────────── */

function formatDiag(diag) {
  if (!diag) return '';
  const parts = [];
  if (diag.generation_time_s != null) parts.push(`${diag.generation_time_s.toFixed(2)}s`);
  if (diag.tokens_per_second != null) parts.push(`${diag.tokens_per_second.toFixed(1)} t/s`);
  if (diag.token_count != null) parts.push(`${diag.token_count} tok`);
  if (diag.input_tokens != null) parts.push(`in:${diag.input_tokens}`);
  if (diag.reasoning_tokens != null) parts.push(`think:${diag.reasoning_tokens}`);
  if (diag.time_to_first_token != null) parts.push(`TTFT:${diag.time_to_first_token.toFixed(1)}s`);
  return parts.join(' | ');
}

/* ── Message ID generator ──────────────────────────────────────── */

function msgId(prefix) {
  return (prefix || 'msg') + '-' + Date.now() + '-' + Math.random().toString(36).slice(2,6);
}
