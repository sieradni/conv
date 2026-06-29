"use strict";

/* ── WebSocket connection management ──────────────────────────── */

let socket = null;

function connectWS() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const url = `${proto}//${location.host}/ws/${window.sessionId}`;
  socket = new WebSocket(url);
  socket.onopen = () => {
    setConnection(true);
    loadChatHistory();
  };
  socket.onclose = () => {
    setConnection(false);
    setTimeout(connectWS, 2000);
  };
  socket.onerror = () => setConnection(false);
  socket.onmessage = e => {
    try {
      const evt = JSON.parse(e.data);
      logRawEvent(evt);
      handleMessage(evt);
    } catch(_) {}
  };
}

function setConnection(ok) {
  const dot = $('connection-dot');
  const badge = $('connection-badge');
  if (ok) {
    if (dot) dot.className = 'w-1.5 h-1.5 rounded-full bg-emerald-400';
    if (badge) badge.className = 'badge bg-emerald-500/10 text-emerald-400 border border-emerald-500/20';
  } else {
    if (dot) dot.className = 'w-1.5 h-1.5 rounded-full bg-rose-500';
    if (badge) badge.className = 'badge bg-rose-500/10 text-rose-400 border border-rose-500/20';
  }
}
