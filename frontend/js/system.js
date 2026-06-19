"use strict";

/* ── System Resources Monitor ─────────────────────────────────── */

let _sysTimer = null;

function initSystemMonitor() {
  const el = $('sys-resources');
  if (!el) return;
  el.style.display = 'flex';
  pollSystemResources();
  _sysTimer = setInterval(pollSystemResources, 5000);
}

async function pollSystemResources() {
  try {
    const r = await fetch('/api/system/resources');
    if (!r.ok) return;
    const d = await r.json();
    updateSysDisplay(d);
  } catch(_) {}
}

function updateSysDisplay(d) {
  const cpuText = `CPU ${d.cpu_percent ?? '?'}%`;
  const memText = d.memory_used_gb != null && d.memory_total_gb != null
    ? `MEM ${d.memory_used_gb}/${d.memory_total_gb}GB`
    : d.memory_percent != null ? `MEM ${d.memory_percent}%` : '';

  let gpuText = '';
  if (d.gpu) {
    const g = Array.isArray(d.gpu) ? d.gpu[0] : d.gpu;
    gpuText = `GPU ${g.utilization_percent ?? '?'}% ${g.memory_used_mb ?? '?'}/${g.memory_total_mb ?? '?'}MB`;
  }

  let battText = '';
  if (d.battery) {
    const plug = d.battery.power_plugged ? '\u26A1' : '\u26A0';
    const pct = d.battery.percent ?? '?';
    const pw = d.battery.power_watts;
    if (pw != null && pw > 0) {
      const sign = d.battery.power_plugged ? '+' : '-';
      battText = `${plug} ${pct}% (${sign}${pw}W)`;
    } else {
      battText = `${plug} ${pct}%`;
    }
  }

  setSysText('sys-cpu', cpuText);
  setSysText('sys-mem', memText);
  setSysText('sys-gpu', gpuText);
  setSysText('sys-batt', battText);

  showIfNeeded('sys-sep1', memText);
  showIfNeeded('sys-sep2', gpuText);
  showIfNeeded('sys-sep3', battText);
}

function setSysText(id, text) {
  const el = $(id);
  if (!el) return;
  el.textContent = text;
  el.style.display = text ? '' : 'none';
}

function showIfNeeded(id, nextHasContent) {
  const el = $(id);
  if (!el) return;
  el.style.display = nextHasContent ? '' : 'none';
}
