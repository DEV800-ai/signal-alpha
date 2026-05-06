"""Web UI for the wiki validator.

Run with:
    uv run python -m signalalpha.wiki.app
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import duckdb
import uvicorn
from fastapi import FastAPI, Form, Query
from fastapi.responses import HTMLResponse, JSONResponse

from signalalpha.config import DB_PATH
from signalalpha.wiki.autogen import WIKI_ROOT, run_autogen, _signal_status
from signalalpha.wiki.cli import _to_dict
from signalalpha.wiki.validate import validate

app = FastAPI(title="SignalAlpha Validator")


# ── Signals dashboard data ────────────────────────────────────────────────────

def _signals_data() -> dict:
    try:
        con = duckdb.connect(str(DB_PATH), read_only=True)
    except Exception as e:
        return {"error": str(e)}

    def q(sql):
        try:
            return con.execute(sql).fetchall()
        except Exception:
            return []

    try:
        rows = q("""
            SELECT
                run_id, signal_name, hold_days,
                n_events, event_window_start, event_window_end,
                hit_rate, mean_return, mean_alpha_sector,
                p_value_vs_sector, sharpe_ann, max_drawdown,
                run_at
            FROM signal_runs
            ORDER BY p_value_vs_sector ASC NULLS LAST, run_id DESC
        """)
        cols = [
            "run_id", "signal_name", "hold_days",
            "n_events", "event_window_start", "event_window_end",
            "hit_rate", "mean_return", "mean_alpha_sector",
            "p_value_vs_sector", "sharpe_ann", "max_drawdown",
            "run_at",
        ]
        signals = []
        for r in rows:
            d = dict(zip(cols, r))
            d["status"] = _signal_status(d)
            d["run_at"] = str(d["run_at"])[:10] if d["run_at"] else None
            d["event_window_start"] = str(d["event_window_start"])[:10] if d["event_window_start"] else None
            d["event_window_end"] = str(d["event_window_end"])[:10] if d["event_window_end"] else None
            # Round floats
            for k in ("hit_rate", "mean_return", "mean_alpha_sector", "p_value_vs_sector", "sharpe_ann", "max_drawdown"):
                if d[k] is not None:
                    d[k] = round(float(d[k]), 6)
            signals.append(d)
    finally:
        con.close()

    return {"signals": signals}


# ── Wiki page browser ─────────────────────────────────────────────────────────

def _list_wiki_pages() -> list[dict]:
    pages = []
    for kind in ("signals", "companies/public", "companies/private", "sectors"):
        folder = WIKI_ROOT / kind
        if not folder.exists():
            continue
        for p in sorted(folder.glob("*.md")):
            pages.append({
                "path": str(p.relative_to(WIKI_ROOT.parent)),
                "name": p.stem,
                "type": kind.split("/")[0],
                "group": kind,
            })
    return pages


# ── HTML ──────────────────────────────────────────────────────────────────────

_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SignalAlpha</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: 'Segoe UI', system-ui, sans-serif;
    background: #0f1117; color: #e2e8f0;
    min-height: 100vh; display: flex; flex-direction: column; align-items: center;
    padding: 1.5rem 1rem;
  }
  header {
    width: 100%; max-width: 1200px;
    display: flex; align-items: center; gap: 1.2rem;
    margin-bottom: 1.5rem;
  }
  header h1 { font-size: 1.4rem; font-weight: 700; }

  /* Tabs */
  .tabs {
    width: 100%; max-width: 1200px;
    display: flex; gap: 0; border-bottom: 1px solid #2d3348;
    margin-bottom: 1.5rem;
  }
  .tab-btn {
    background: none; border: none; color: #64748b;
    padding: .55rem 1.2rem; font-size: .88rem; font-weight: 600;
    cursor: pointer; border-bottom: 2px solid transparent;
    margin-bottom: -1px; transition: color .12s, border-color .12s;
  }
  .tab-btn:hover { color: #94a3b8; }
  .tab-btn.active { color: #a5b4fc; border-bottom-color: #6366f1; }

  .tab-panel { display: none; width: 100%; max-width: 1200px; }
  .tab-panel.active { display: block; }

  /* Cards */
  .card {
    background: #1e2330; border: 1px solid #2d3348;
    border-radius: 10px; padding: 1.1rem; margin-bottom: 1rem;
  }
  .card-title {
    font-size: .75rem; color: #64748b;
    text-transform: uppercase; letter-spacing: .07em;
    margin-bottom: .75rem; display: flex; align-items: center; gap: .5rem;
  }
  .card-title .actions { margin-left: auto; display: flex; gap: .4rem; }

  /* Signals table */
  .tbl-wrap { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; font-size: .82rem; }
  thead th {
    text-align: left; color: #475569; font-size: .72rem;
    text-transform: uppercase; letter-spacing: .06em;
    padding: .45rem .7rem; border-bottom: 1px solid #2d3348;
    white-space: nowrap; cursor: pointer; user-select: none;
  }
  thead th:hover { color: #94a3b8; }
  thead th .sort-arrow { margin-left: .25rem; opacity: .4; }
  thead th.sorted .sort-arrow { opacity: 1; color: #a5b4fc; }
  tbody tr { border-bottom: 1px solid #1a1c2e; transition: background .1s; }
  tbody tr:hover { background: #252a3a; cursor: pointer; }
  tbody td { padding: .45rem .7rem; white-space: nowrap; }
  .td-name { font-weight: 600; color: #e2e8f0; max-width: 220px; overflow: hidden; text-overflow: ellipsis; }
  .td-mono { font-family: monospace; font-size: .78rem; }

  .status-pill {
    display: inline-block; padding: .15rem .55rem;
    border-radius: 999px; font-size: .68rem; font-weight: 700; letter-spacing: .04em;
  }
  .status-validated  { background: #14532d; color: #4ade80; }
  .status-borderline { background: #78350f; color: #fbbf24; }
  .status-graveyard  { background: #1f2937; color: #6b7280; }

  .num-pos { color: #4ade80; }
  .num-neg { color: #f87171; }
  .num-neu { color: #94a3b8; }

  /* Empty state */
  .empty-state {
    text-align: center; padding: 3rem 1rem; color: #475569; font-size: .9rem;
  }
  .empty-state p { margin-top: .4rem; font-size: .78rem; }

  /* Wiki editor layout */
  .editor-layout {
    display: grid;
    grid-template-columns: 220px 1fr;
    gap: 1rem;
    align-items: start;
  }
  @media(max-width:760px){ .editor-layout { grid-template-columns: 1fr; } }

  /* Page browser */
  .page-group-label {
    font-size: .7rem; color: #475569; text-transform: uppercase;
    letter-spacing: .06em; margin: .6rem 0 .3rem; padding: 0 .3rem;
  }
  .page-item {
    padding: .35rem .5rem; border-radius: 6px; cursor: pointer;
    font-size: .8rem; color: #94a3b8; white-space: nowrap;
    overflow: hidden; text-overflow: ellipsis;
    transition: background .12s, color .12s;
  }
  .page-item:hover { background: #2d3348; color: #e2e8f0; }
  .page-item.active { background: #312e81; color: #a5b4fc; }
  .no-pages { color: #475569; font-size: .78rem; font-style: italic; }

  /* Editor */
  textarea {
    width: 100%; height: 380px;
    background: #0f1117; color: #e2e8f0;
    border: 1px solid #2d3348; border-radius: 8px;
    padding: .75rem; font-family: 'Fira Code', monospace; font-size: .78rem;
    resize: vertical; outline: none;
  }
  textarea:focus { border-color: #6366f1; }

  .toolbar { display: flex; gap: .6rem; align-items: center; margin-top: .75rem; flex-wrap: wrap; }
  .file-btn {
    cursor: pointer; background: #2d3348; color: #94a3b8;
    padding: .38rem .8rem; border-radius: 7px; font-size: .8rem;
    border: 1px solid #3d4560; transition: background .12s;
  }
  .file-btn:hover { background: #3d4560; }
  input[type=file] { display: none; }
  #filename { font-size: .75rem; color: #475569; }

  button {
    background: #6366f1; color: #fff; border: none;
    padding: .42rem 1rem; border-radius: 7px; font-size: .84rem;
    font-weight: 600; cursor: pointer; transition: background .12s;
  }
  button:hover { background: #4f46e5; }
  button:disabled { background: #2d3348; color: #475569; cursor: not-allowed; }
  button.secondary {
    background: #1e2330; border: 1px solid #2d3348; color: #94a3b8; font-weight: 500;
  }
  button.secondary:hover { background: #2d3348; }
  button.success { background: #166534; }
  button.success:hover { background: #14532d; }

  .spinner { display:none; width:15px; height:15px; border:2px solid #2d3348;
    border-top-color:#6366f1; border-radius:50%; animation:spin .7s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* Result */
  #result { display: none; }
  .verdict { display:flex; align-items:center; gap:.5rem; font-size:1.1rem; font-weight:700; margin-bottom:.9rem; }
  .verdict.pass { color: #4ade80; }
  .verdict.fail { color: #f87171; }
  .badge { font-size:.66rem; padding:.16rem .45rem; border-radius:999px; font-weight:700; letter-spacing:.04em; }
  .badge.pass { background:#14532d; color:#4ade80; }
  .badge.fail { background:#7f1d1d; color:#f87171; }
  .badge.warn { background:#78350f; color:#fbbf24; }

  .summary-row { display:flex; gap:.6rem; margin-bottom:.9rem; flex-wrap:wrap; }
  .stat { background:#0f1117; border:1px solid #2d3348; border-radius:7px; padding:.35rem .7rem; font-size:.78rem; }
  .stat b { margin-right:.25rem; }

  .passes { display:flex; flex-direction:column; gap:.5rem; }
  .pass-row { border:1px solid #2d3348; border-radius:7px; overflow:hidden; }
  .pass-hdr {
    display:flex; align-items:center; gap:.5rem;
    padding:.55rem .8rem; background:#16192a; cursor:pointer; user-select:none;
  }
  .pass-hdr:hover { background:#1e2330; }
  .pass-name { font-weight:600; font-size:.84rem; }
  .pass-counts { margin-left:auto; display:flex; gap:.35rem; }
  .pass-body { padding:.65rem .8rem; background:#0f1117; display:none; }
  .pass-body.open { display:block; }
  .issue-list { list-style:none; display:flex; flex-direction:column; gap:.4rem; }
  .issue { border-left:3px solid; padding:.4rem .6rem; border-radius:0 5px 5px 0; background:#1a1c2e; font-size:.78rem; }
  .issue.fail { border-color:#f87171; }
  .issue.warn { border-color:#fbbf24; }
  .issue-rule { font-weight:700; font-family:monospace; font-size:.73rem; margin-bottom:.15rem; }
  .issue-msg { color:#cbd5e1; line-height:1.4; }
  .issue-loc { color:#475569; font-size:.7rem; margin-top:.15rem; }
  .empty { color:#475569; font-size:.78rem; font-style:italic; }

  /* Toast */
  #toast {
    position:fixed; bottom:1.5rem; right:1.5rem;
    background:#1e2330; border:1px solid #2d3348; border-radius:8px;
    padding:.6rem 1rem; font-size:.8rem; color:#e2e8f0;
    opacity:0; transition:opacity .2s; pointer-events:none;
  }
  #toast.show { opacity:1; }
</style>
</head>
<body>

<header>
  <h1>SignalAlpha</h1>
</header>

<div class="tabs">
  <button class="tab-btn active" onclick="switchTab('signals', this)">Signals</button>
  <button class="tab-btn" onclick="switchTab('editor', this)">Wiki Editor</button>
</div>

<!-- ═══════════════════════════════════════════════════════ SIGNALS TAB -->
<div class="tab-panel active" id="tab-signals">
  <div class="card">
    <div class="card-title">
      Signal Runs
      <span class="actions">
        <button class="secondary" style="font-size:.7rem;padding:.25rem .5rem" onclick="loadSignals()">↻ Refresh</button>
      </span>
    </div>
    <div id="signals-content"><p class="no-pages">Loading…</p></div>
  </div>
</div>

<!-- ═══════════════════════════════════════════════════════ EDITOR TAB -->
<div class="tab-panel" id="tab-editor">
  <div class="editor-layout">

    <!-- Left: page browser + autogen -->
    <div>
      <div class="card">
        <div class="card-title">
          Wiki Pages
          <span class="actions">
            <button class="secondary" style="font-size:.7rem;padding:.25rem .5rem" onclick="loadPages()">↻</button>
          </span>
        </div>
        <div id="page-list"><p class="no-pages">Loading…</p></div>
      </div>
      <div class="card">
        <div class="card-title">Auto-generator</div>
        <p style="font-size:.75rem;color:#64748b;margin-bottom:.6rem">Scaffold missing pages and refresh AUTOGEN sections from the DB.</p>
        <button class="success" onclick="runAutogen()" id="autogenBtn">Run Autogen</button>
        <div id="autogen-out" style="margin-top:.6rem;font-size:.75rem;color:#94a3b8;white-space:pre-wrap"></div>
      </div>
    </div>

    <!-- Right: editor + result -->
    <div>
      <div class="card">
        <div class="card-title">Editor</div>
        <textarea id="content" placeholder="Click a page on the left, or load a .md file…"></textarea>
        <div class="toolbar">
          <label class="file-btn" for="fileInput">Load file</label>
          <input type="file" id="fileInput" accept=".md">
          <span id="filename"></span>
          <button onclick="runValidate()" id="runBtn">Validate</button>
          <div class="spinner" id="spinner"></div>
        </div>
      </div>

      <div class="card" id="result">
        <div class="card-title">Validation Result</div>
        <div id="verdict" class="verdict"></div>
        <div class="summary-row" id="summary"></div>
        <div class="passes" id="passes"></div>
      </div>
    </div>

  </div>
</div>

<div id="toast"></div>

<script>
const PASS_NAMES = {
  1:'Pass 1 — Frontmatter', 2:'Pass 2 — Structure',
  3:'Pass 3 — Citations',   4:'Pass 4 — Claim Types'
};

// ── Tabs ──────────────────────────────────────────────────────────────────────
function switchTab(name, btn) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('tab-' + name).classList.add('active');
}

// ── Toast ─────────────────────────────────────────────────────────────────────
function toast(msg, ms=2500) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), ms);
}

// ── Signals table ─────────────────────────────────────────────────────────────
let _signals = [];
let _sortCol = 'p_value_vs_sector';
let _sortAsc = true;

const STATUS_ORDER = { validated: 0, borderline: 1, graveyard: 2 };

async function loadSignals() {
  document.getElementById('signals-content').innerHTML = '<p class="no-pages">Loading…</p>';
  try {
    const data = await (await fetch('/signals')).json();
    if (data.error) throw new Error(data.error);
    _signals = data.signals;
    renderSignals();
  } catch(e) {
    document.getElementById('signals-content').innerHTML =
      '<p style="color:#f87171;font-size:.8rem">Error: ' + escHtml(e.message) + '</p>';
  }
}

function sortSignals(col) {
  if (_sortCol === col) { _sortAsc = !_sortAsc; }
  else { _sortCol = col; _sortAsc = true; }
  renderSignals();
}

function renderSignals() {
  const cols = [
    { key: 'signal_name',        label: 'Signal' },
    { key: 'status',             label: 'Status' },
    { key: 'run_id',             label: 'Run' },
    { key: 'n_events',           label: 'N events' },
    { key: 'hit_rate',           label: 'Hit rate' },
    { key: 'mean_return',        label: 'Mean return' },
    { key: 'mean_alpha_sector',  label: 'Alpha vs sector' },
    { key: 'p_value_vs_sector',  label: 'p-value' },
    { key: 'sharpe_ann',         label: 'Sharpe' },
    { key: 'hold_days',          label: 'Hold days' },
    { key: 'run_at',             label: 'Run date' },
  ];

  const sorted = [..._signals].sort((a, b) => {
    let av = a[_sortCol], bv = b[_sortCol];
    if (_sortCol === 'status') { av = STATUS_ORDER[av] ?? 99; bv = STATUS_ORDER[bv] ?? 99; }
    if (av === null || av === undefined) return 1;
    if (bv === null || bv === undefined) return -1;
    return _sortAsc ? (av > bv ? 1 : -1) : (av < bv ? 1 : -1);
  });

  if (!sorted.length) {
    document.getElementById('signals-content').innerHTML =
      '<div class="empty-state">No signal runs found in the database.<p>Run a backtest to populate signal_runs.</p></div>';
    return;
  }

  let thead = '<thead><tr>' + cols.map(c => {
    const sorted = _sortCol === c.key;
    const arrow = sorted ? (_sortAsc ? ' ▲' : ' ▼') : ' ↕';
    return `<th class="${sorted?'sorted':''}" onclick="sortSignals('${c.key}')">${escHtml(c.label)}<span class="sort-arrow">${arrow}</span></th>`;
  }).join('') + '</tr></thead>';

  let tbody = '<tbody>' + sorted.map(r => {
    const statusPill = `<span class="status-pill status-${r.status}">${r.status}</span>`;
    const pct = v => v === null || v === undefined ? '<span class="num-neu">—</span>'
      : `<span class="${v>=0?'num-pos':'num-neg'}">${v>=0?'+':''}${(v*100).toFixed(1)}%</span>`;
    const num = (v, d=2) => v === null || v === undefined ? '<span class="num-neu">—</span>'
      : `<span class="num-neu">${v.toFixed(d)}</span>`;
    const pval = v => v === null || v === undefined ? '<span class="num-neu">—</span>'
      : `<span class="${v<0.05?'num-pos':v<0.10?'num-neg':'num-neu'}">${v.toFixed(4)}</span>`;
    return `<tr onclick="openInEditor('${escAttr(r.signal_name)}')">
      <td class="td-name">${escHtml(r.signal_name)}</td>
      <td>${statusPill}</td>
      <td class="td-mono">#${r.run_id}</td>
      <td class="td-mono">${r.n_events ?? '—'}</td>
      <td>${pct(r.hit_rate)}</td>
      <td>${pct(r.mean_return)}</td>
      <td>${pct(r.mean_alpha_sector)}</td>
      <td class="td-mono">${pval(r.p_value_vs_sector)}</td>
      <td>${num(r.sharpe_ann)}</td>
      <td class="td-mono">${r.hold_days ?? '—'}d</td>
      <td class="td-mono">${r.run_at ?? '—'}</td>
    </tr>`;
  }).join('') + '</tbody>';

  document.getElementById('signals-content').innerHTML =
    '<div class="tbl-wrap"><table>' + thead + tbody + '</table></div>';
}

function openInEditor(signalName) {
  // Switch to editor tab and try to load the matching wiki page
  const editorBtn = document.querySelector('[onclick="switchTab(\'editor\', this)"]');
  switchTab('editor', editorBtn);
  // Find matching page
  fetch('/wiki-pages').then(r=>r.json()).then(data => {
    loadPages(data.pages);
    // Clean signal name to match page stem
    const slug = signalName.replace(/[^\w.\-]/g, '_').replace(/^_+|_+$/g, '');
    const match = data.pages.find(p => p.name === slug || p.name.includes(slug));
    if (match) {
      setTimeout(() => {
        const el = document.querySelector(`.page-item[data-path="${match.path}"]`);
        if (el) loadPage(el, match.path);
      }, 50);
    }
  });
}

// ── Page browser ──────────────────────────────────────────────────────────────
let _activePage = null;

async function loadPages(pages) {
  const el = document.getElementById('page-list');
  if (!pages) {
    el.innerHTML = '<p class="no-pages">Loading…</p>';
    try {
      pages = (await (await fetch('/wiki-pages')).json()).pages;
    } catch(e) {
      el.innerHTML = '<p class="no-pages">Error loading pages.</p>';
      return;
    }
  }
  renderPages(pages);
}

function renderPages(pages) {
  const el = document.getElementById('page-list');
  if (!pages.length) {
    el.innerHTML = '<p class="no-pages">No wiki pages yet — run Autogen.</p>';
    return;
  }
  const byGroup = {};
  pages.forEach(p => { (byGroup[p.group] = byGroup[p.group] || []).push(p); });
  const labels = {
    'signals': 'Signals',
    'companies/public': 'Companies (public)',
    'companies/private': 'Companies (private)',
    'sectors': 'Sectors',
  };
  let html = '';
  for (const [group, items] of Object.entries(byGroup)) {
    html += `<div class="page-group-label">${labels[group]||group}</div>`;
    items.forEach(p => {
      html += `<div class="page-item" data-path="${escAttr(p.path)}" onclick="loadPage(this, '${escAttr(p.path)}')">${escHtml(p.name)}</div>`;
    });
  }
  el.innerHTML = html;
  if (_activePage) {
    document.querySelectorAll('.page-item').forEach(el => {
      if (el.dataset.path === _activePage) el.classList.add('active');
    });
  }
}

async function loadPage(el, path) {
  document.querySelectorAll('.page-item').forEach(x => x.classList.remove('active'));
  el.classList.add('active');
  _activePage = path;
  try {
    const data = await (await fetch('/wiki-page-content?path=' + encodeURIComponent(path))).json();
    document.getElementById('content').value = data.content;
    document.getElementById('filename').textContent = path.split('/').pop();
    document.getElementById('result').style.display = 'none';
  } catch(e) { toast('Failed to load page: ' + e.message); }
}

// ── File picker ───────────────────────────────────────────────────────────────
document.getElementById('fileInput').addEventListener('change', e => {
  const file = e.target.files[0];
  if (!file) return;
  document.getElementById('filename').textContent = file.name;
  const reader = new FileReader();
  reader.onload = ev => document.getElementById('content').value = ev.target.result;
  reader.readAsText(file);
});

// ── Validate ──────────────────────────────────────────────────────────────────
async function runValidate() {
  const content = document.getElementById('content').value.trim();
  if (!content) { alert('Paste or load a wiki page first.'); return; }
  const btn = document.getElementById('runBtn');
  const spinner = document.getElementById('spinner');
  btn.disabled = true; spinner.style.display = 'block';
  document.getElementById('result').style.display = 'none';
  try {
    const fd = new FormData();
    fd.append('content', content);
    renderResult(await (await fetch('/validate', {method:'POST', body:fd})).json());
  } catch(e) { alert('Error: ' + e.message); }
  finally { btn.disabled = false; spinner.style.display = 'none'; }
}

function renderResult(data) {
  const isPass = data.verdict === 'PASS';
  const vEl = document.getElementById('verdict');
  vEl.className = 'verdict ' + (isPass ? 'pass' : 'fail');
  vEl.innerHTML = (isPass ? '✅' : '❌') + ' ' + data.verdict;
  document.getElementById('summary').innerHTML =
    stat(data.failures.length, 'failure') +
    stat(data.warnings.length, 'warning') +
    stat(data.pass_results.length, 'pass', 'es run');
  const passesEl = document.getElementById('passes');
  passesEl.innerHTML = '';
  data.pass_results.forEach(p => {
    const hasFail = p.failures.length > 0, hasWarn = p.warnings.length > 0;
    const sb = hasFail ? badge('fail','FAIL') : hasWarn ? badge('warn','WARN') : badge('pass','OK');
    const counts = [
      p.failures.length ? badge('fail', p.failures.length + ' failure' + (p.failures.length!==1?'s':'')) : '',
      p.warnings.length ? badge('warn', p.warnings.length + ' warning' + (p.warnings.length!==1?'s':'')) : '',
    ].filter(Boolean).join('');
    const issues = [...p.failures.map(f=>issueHTML(f,'fail')), ...p.warnings.map(w=>issueHTML(w,'warn'))];
    const body = issues.length ? '<ul class="issue-list">'+issues.join('')+'</ul>' : '<p class="empty">No issues.</p>';
    const row = document.createElement('div');
    row.className = 'pass-row';
    row.innerHTML =
      '<div class="pass-hdr" onclick="toggle(this)">' +
        sb + '<span class="pass-name">' + (PASS_NAMES[p.pass_num]||'Pass '+p.pass_num) + '</span>' +
        '<span class="pass-counts">'+counts+'</span>' +
      '</div>' +
      '<div class="pass-body'+(hasFail||hasWarn?' open':'')+'">'+body+'</div>';
    passesEl.appendChild(row);
  });
  document.getElementById('result').style.display = 'block';
  document.getElementById('result').scrollIntoView({behavior:'smooth'});
}

// ── Auto-generator ────────────────────────────────────────────────────────────
async function runAutogen() {
  const btn = document.getElementById('autogenBtn');
  const out = document.getElementById('autogen-out');
  btn.disabled = true;
  out.textContent = 'Running…';
  try {
    const data = await (await fetch('/autogen', {method:'POST'})).json();
    out.textContent = data.results.join('\n') || 'Nothing to update.';
    toast('Autogen done — ' + data.results.length + ' page(s) affected.');
    loadPages();
  } catch(e) {
    out.textContent = 'Error: ' + e.message;
  } finally { btn.disabled = false; }
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function stat(n, label, suffix='s') {
  return '<div class="stat"><b>'+n+'</b> '+label+(n!==1?suffix:'')+'</div>';
}
function badge(cls, text) { return '<span class="badge '+cls+'">'+escHtml(String(text))+'</span>'; }
function issueHTML(issue, kind) {
  return '<li class="issue '+kind+'">'+
    '<div class="issue-rule">'+escHtml(issue.rule)+'</div>'+
    '<div class="issue-msg">'+escHtml(issue.message)+'</div>'+
    (issue.location?'<div class="issue-loc">'+escHtml(issue.location)+'</div>':'')+
    '</li>';
}
function toggle(h) { h.nextElementSibling.classList.toggle('open'); }
function escHtml(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function escAttr(s) { return String(s).replace(/'/g,"\\'"); }

// Boot
loadSignals();
loadPages();
</script>
</body>
</html>
"""


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    return _HTML


@app.get("/signals")
async def signals():
    return JSONResponse(_signals_data())


@app.get("/wiki-pages")
async def wiki_pages():
    return JSONResponse({"pages": _list_wiki_pages()})


@app.get("/wiki-page-content")
async def wiki_page_content(path: str = Query(...)):
    full = WIKI_ROOT.parent / path
    if not full.exists() or not full.is_file():
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse({"content": full.read_text(encoding="utf-8")})


@app.post("/validate")
async def validate_endpoint(content: str = Form(...)):
    with tempfile.NamedTemporaryFile(suffix=".md", mode="w", encoding="utf-8", delete=False) as f:
        f.write(content)
        tmp_path = Path(f.name)
    try:
        db = duckdb.connect(str(DB_PATH), read_only=True)
        try:
            result = validate(tmp_path, db)
        finally:
            db.close()
    finally:
        tmp_path.unlink(missing_ok=True)
    return JSONResponse(_to_dict(result))


@app.post("/autogen")
async def autogen_endpoint():
    results = run_autogen()
    return JSONResponse({"results": results})


if __name__ == "__main__":
    uvicorn.run("signalalpha.wiki.app:app", host="127.0.0.1", port=8000, reload=True)
