"""Web UI — Daily Signal Brief + Wiki Editor.

Run with:
    uv run python -m signalalpha.wiki.app
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import duckdb
import uvicorn
import os

from fastapi import BackgroundTasks, FastAPI, Form, Query, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse

from signalalpha.config import DB_PATH
from signalalpha.wiki.autogen import WIKI_ROOT, run_autogen
from signalalpha.wiki.brief import build_daily_brief
from signalalpha.wiki.cli import _to_dict
from signalalpha.wiki.validate import validate

app = FastAPI(title="SignalAlpha")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _open_db(read_only: bool = True) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(DB_PATH), read_only=read_only)


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
    display: flex; align-items: center; gap: 1rem;
    margin-bottom: 1rem;
  }
  header h1 { font-size: 1.3rem; font-weight: 700; letter-spacing: -.02em; }
  header .tagline { color: #7a8aaa; font-size: .8rem; }

  /* Tabs */
  .tabs {
    width: 100%; max-width: 1200px;
    display: flex; border-bottom: 1px solid #2d3348;
    margin-bottom: 1.5rem;
  }
  .tab-btn {
    background: none; border: none; color: #8899bb;
    padding: .55rem 1.2rem; font-size: .88rem; font-weight: 600;
    cursor: pointer; border-bottom: 2px solid transparent;
    margin-bottom: -1px; transition: color .12s, border-color .12s;
  }
  .tab-btn:hover { color: #94a3b8; }
  .tab-btn.active { color: #a5b4fc; border-bottom-color: #6366f1; }

  .tab-panel { display: none; width: 100%; max-width: 1200px; }
  .tab-panel.active { display: block; }

  /* Card */
  .card {
    background: #1e2330; border: 1px solid #2d3348;
    border-radius: 10px; padding: 1.1rem; margin-bottom: 1rem;
  }
  .card-title {
    font-size: .72rem; color: #8899bb;
    text-transform: uppercase; letter-spacing: .07em;
    margin-bottom: .85rem; display: flex; align-items: center; gap: .5rem;
  }
  .card-title .actions { margin-left: auto; display: flex; gap: .4rem; }

  /* ── Daily Brief ──────────────────────────────────────── */
  .brief-grid {
    display: flex; flex-direction: column; gap: .6rem;
  }
  .signal-card {
    background: #141720; border: 1px solid #2d3348; border-radius: 9px;
    padding: .85rem 1rem; display: grid;
    grid-template-columns: 200px 1fr auto;
    gap: .5rem 1.2rem; align-items: start;
    cursor: pointer; transition: border-color .15s, background .15s;
  }
  .signal-card:hover { border-color: #4f46e5; background: #191d2a; }

  .sc-name { font-weight: 700; font-size: .9rem; color: #e2e8f0; margin-bottom: .3rem; }
  .sc-meta { font-size: .73rem; color: #7a8aaa; }

  .sc-stats {
    display: flex; flex-wrap: wrap; gap: .4rem .9rem; align-items: center;
  }
  .stat-item { font-size: .78rem; }
  .stat-label { color: #8899bb; margin-right: .2rem; }
  .stat-val { font-weight: 600; }
  .pos { color: #4ade80; }
  .neg { color: #f87171; }
  .neu { color: #c0cce0; }
  .amber { color: #fbbf24; }

  .sc-right { display: flex; flex-direction: column; align-items: flex-end; gap: .4rem; }

  .status-pill {
    display: inline-block; padding: .18rem .6rem;
    border-radius: 999px; font-size: .68rem; font-weight: 700; letter-spacing: .04em;
    white-space: nowrap;
  }
  .pill-validated  { background: #14532d; color: #4ade80; }
  .pill-borderline { background: #78350f; color: #fbbf24; }
  .pill-graveyard  { background: #1f2937; color: #6b7280; }

  .ctx-pill {
    display: inline-flex; align-items: center; gap: .3rem;
    padding: .15rem .5rem; border-radius: 5px; font-size: .68rem; font-weight: 600;
  }
  .ctx-current { background: #0c2120; color: #34d399; border: 1px solid #065f46; }
  .ctx-stale   { background: #1c1708; color: #fbbf24; border: 1px solid #78350f; }
  .ctx-missing { background: #1a1a1a; color: #6b7280; border: 1px solid #374151; }

  .wiki-link {
    font-size: .7rem; color: #6366f1; text-decoration: none;
    background: none; border: none; cursor: pointer; padding: 0;
  }
  .wiki-link:hover { color: #a5b4fc; text-decoration: underline; }

  /* Drilldown */
  .drilldown {
    display: none; margin-top: .6rem;
    border-top: 1px solid #2d3348; padding-top: .7rem;
  }
  .drilldown.open { display: block; }
  .drilldown-hdr {
    font-size: .72rem; color: #8899bb; text-transform: uppercase;
    letter-spacing: .06em; margin-bottom: .5rem;
    display: flex; align-items: center; gap: .5rem;
  }
  .ev-tbl { width: 100%; border-collapse: collapse; font-size: .75rem; }
  .ev-tbl th {
    text-align: left; color: #8899bb; font-size: .68rem;
    text-transform: uppercase; letter-spacing: .05em;
    padding: .3rem .5rem; border-bottom: 1px solid #2d3348;
  }
  .ev-tbl td { padding: .28rem .5rem; border-bottom: 1px solid #141720; color: #c0cce0; }
  .ev-tbl tr:hover td { background: #1e2330; }
  .ev-loading { color: #7a8aaa; font-size: .75rem; font-style: italic; padding: .5rem 0; }

  /* Divider */
  .brief-meta {
    font-size: .73rem; color: #7a8aaa; margin-bottom: .85rem;
    display: flex; align-items: center; gap: .5rem;
  }

  /* Empty / loading */
  .state-msg { color: #7a8aaa; font-size: .82rem; font-style: italic; padding: 1.5rem 0; text-align: center; }

  /* ── Wiki Editor ──────────────────────────────────────── */
  .editor-layout {
    display: grid; grid-template-columns: 220px 1fr;
    gap: 1rem; align-items: start;
  }
  @media(max-width:760px){ .editor-layout { grid-template-columns: 1fr; } }

  .page-group-label {
    font-size: .7rem; color: #7a8aaa; text-transform: uppercase;
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
  .no-pages { color: #7a8aaa; font-size: .78rem; font-style: italic; }

  textarea {
    width: 100%; height: 400px;
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
  #filename { font-size: .75rem; color: #7a8aaa; }

  button {
    background: #6366f1; color: #fff; border: none;
    padding: .42rem 1rem; border-radius: 7px; font-size: .84rem;
    font-weight: 600; cursor: pointer; transition: background .12s;
  }
  button:hover { background: #4f46e5; }
  button:disabled { background: #2d3348; color: #7a8aaa; cursor: not-allowed; }
  button.secondary {
    background: #1e2330; border: 1px solid #2d3348; color: #94a3b8; font-weight: 500;
  }
  button.secondary:hover { background: #2d3348; }
  button.success { background: #166534; }
  button.success:hover { background: #14532d; }

  .spinner { display:none; width:15px; height:15px; border:2px solid #2d3348;
    border-top-color:#6366f1; border-radius:50%; animation:spin .7s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* Validation result */
  #result { display: none; }
  .verdict { display:flex; align-items:center; gap:.5rem; font-size:1.05rem; font-weight:700; margin-bottom:.9rem; }
  .verdict.pass { color: #4ade80; }
  .verdict.fail { color: #f87171; }
  .badge { font-size:.66rem; padding:.16rem .45rem; border-radius:999px; font-weight:700; letter-spacing:.04em; }
  .badge.pass { background:#14532d; color:#4ade80; }
  .badge.fail { background:#7f1d1d; color:#f87171; }
  .badge.warn { background:#78350f; color:#fbbf24; }
  .summary-row { display:flex; gap:.6rem; margin-bottom:.9rem; flex-wrap:wrap; }
  .stat-box { background:#0f1117; border:1px solid #2d3348; border-radius:7px; padding:.35rem .7rem; font-size:.78rem; }
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
  .issue-loc { color:#7a8aaa; font-size:.7rem; margin-top:.15rem; }
  .empty { color:#7a8aaa; font-size:.78rem; font-style:italic; }

  /* ── How It Works ─────────────────────────────────── */
  .howto-wrap { max-width: 860px; }
  .howto-section { margin-bottom: 2rem; }
  .howto-h2 {
    font-size: .95rem; font-weight: 700; color: #a5b4fc;
    margin-bottom: .75rem; padding-bottom: .4rem;
    border-bottom: 1px solid #2d3348;
  }
  .howto-p { font-size: .83rem; color: #c0cce0; line-height: 1.75; margin-bottom: .6rem; }

  .pipeline { display:flex; align-items:center; flex-wrap:wrap; gap:.3rem; margin:1rem 0; }
  .pipe-step {
    background:#1e2330; border:1px solid #2d3348; border-radius:8px;
    padding:.55rem 1rem;
  }
  .pipe-step strong { display:block; font-size:.68rem; color:#a5b4fc; letter-spacing:.05em; text-transform:uppercase; margin-bottom:.15rem; }
  .pipe-step span { font-size:.76rem; color:#8899bb; }
  .pipe-arrow { color:#4f46e5; font-size:1.1rem; padding:0 .2rem; }

  .metric-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:.75rem; margin-top:.75rem; }
  @media(max-width:760px){ .metric-grid { grid-template-columns:1fr; } }
  .metric-card {
    background:#141720; border:1px solid #2d3348; border-radius:9px; padding:.9rem 1rem;
  }
  .metric-name { font-size:.8rem; font-weight:700; color:#e2e8f0; margin-bottom:.25rem; }
  .metric-abbr { font-size:.68rem; color:#6366f1; font-family:monospace; margin-bottom:.4rem; }
  .metric-desc { font-size:.75rem; color:#8899bb; line-height:1.65; }
  .metric-good { display:inline-block; margin-top:.4rem; font-size:.68rem; color:#4ade80; }
  .metric-bad  { display:inline-block; margin-top:.4rem; font-size:.68rem; color:#f87171; }

  .signal-list { display:flex; flex-direction:column; gap:.6rem; }
  .signal-item { background:#141720; border:1px solid #2d3348; border-radius:8px; padding:.8rem 1rem; }
  .signal-item-name { font-weight:700; color:#e2e8f0; font-size:.85rem; margin-bottom:.3rem; }
  .signal-item-desc { font-size:.75rem; color:#8899bb; line-height:1.65; }

  .dir-explainer { display:grid; grid-template-columns:1fr 1fr; gap:.75rem; margin-top:.75rem; }
  @media(max-width:760px){ .dir-explainer { grid-template-columns:1fr; } }
  .dir-card { border-radius:9px; padding:1rem; }
  .dir-card-long  { background:#0c1a0c; border:1px solid #166534; }
  .dir-card-short { background:#1a0c0c; border:1px solid #7f1d1d; }
  .dir-card-title { font-weight:700; font-size:.88rem; margin-bottom:.5rem; }
  .dir-card-long  .dir-card-title { color:#4ade80; }
  .dir-card-short .dir-card-title { color:#f87171; }
  .dir-card p { font-size:.76rem; color:#8899bb; line-height:1.65; }

  /* ── Top 10 ───────────────────────────────────────── */
  .filter-bar { display:flex; gap:1rem; align-items:center; flex-wrap:wrap; padding:.2rem 0; }
  .filter-group { display:flex; flex-direction:column; gap:.25rem; }
  .filter-label { font-size:.68rem; color:#8899bb; text-transform:uppercase; letter-spacing:.06em; }
  .filter-sel {
    background:#0f1117; color:#e2e8f0; border:1px solid #2d3348;
    border-radius:6px; padding:.32rem .65rem; font-size:.8rem; outline:none; cursor:pointer;
  }
  .filter-sel:focus { border-color:#6366f1; }

  .podium-grid { display:grid; grid-template-columns:1fr 1fr 1fr; gap:1rem; margin-bottom:1rem; }
  @media(max-width:760px) { .podium-grid { grid-template-columns:1fr; } }

  .podium-card {
    background:#1e2330; border:2px solid #2d3348; border-radius:12px;
    padding:1.2rem 1.1rem; position:relative; display:flex; flex-direction:column; gap:.45rem;
    transition:transform .15s;
  }
  .podium-card:hover { transform:translateY(-2px); }
  .podium-card.rank-1 { border-color:#f59e0b; box-shadow:0 0 22px rgba(245,158,11,.13); }
  .podium-card.rank-2 { border-color:#94a3b8; }
  .podium-card.rank-3 { border-color:#b87333; }

  .podium-medal {
    position:absolute; top:.85rem; right:1rem;
    font-size:1.5rem; line-height:1; opacity:.6;
  }

  .podium-ticker { font-size:1.7rem; font-weight:900; letter-spacing:-.03em; }
  .rank-1 .podium-ticker { color:#f59e0b; }
  .rank-2 .podium-ticker { color:#c0cce0; }
  .rank-3 .podium-ticker { color:#cd9a60; }

  .podium-company { font-size:.77rem; color:#8899bb; margin-top:-.2rem; }

  .sector-badge {
    display:inline-block; padding:.12rem .45rem; border-radius:4px;
    font-size:.65rem; font-weight:700; letter-spacing:.04em; white-space:nowrap;
  }
  .sec-ai_infra      { background:#1e1b4b; color:#a5b4fc; border:1px solid #3730a3; }
  .sec-space_defense { background:#064e3b; color:#34d399; border:1px solid #065f46; }
  .sec-telecom       { background:#1c1708; color:#fbbf24; border:1px solid #78350f; }
  .sec-unknown       { background:#1a1a1a; color:#7a8aaa; border:1px solid #374151; }

  .podium-stats { display:flex; flex-wrap:wrap; gap:.35rem .75rem; margin-top:.15rem; }

  .score-bar-wrap { height:4px; background:#2d3348; border-radius:999px; margin-top:.5rem; overflow:hidden; }
  .score-bar-fill { height:100%; border-radius:999px; transition:width .5s; }
  .rank-1 .score-bar-fill { background:#f59e0b; }
  .rank-2 .score-bar-fill { background:#94a3b8; }
  .rank-3 .score-bar-fill { background:#b87333; }
  .rank-other .score-bar-fill { background:#6366f1; }

  .lb-tbl { width:100%; border-collapse:collapse; font-size:.8rem; }
  .lb-tbl th {
    text-align:left; color:#8899bb; font-size:.68rem; text-transform:uppercase;
    letter-spacing:.05em; padding:.4rem .7rem; border-bottom:1px solid #2d3348;
  }
  .lb-tbl td { padding:.42rem .7rem; border-bottom:1px solid #141720; color:#c0cce0; }
  .lb-tbl tbody tr { cursor:pointer; transition:background .1s; }
  .lb-tbl tbody tr:hover td { background:#1e2330; }
  .lb-rank { font-weight:700; color:#7a8aaa; }
  .lb-ticker-cell { font-weight:700; color:#e2e8f0; font-size:.88rem; }
  .lb-bar-cell { width:110px; }
  .lb-bar { height:5px; background:#2d3348; border-radius:999px; margin-top:.3rem; overflow:hidden; }
  .lb-bar-fill { height:100%; background:#6366f1; border-radius:999px; }
  .lb-bar-fill.short { background:#ef4444; }

  .dir-toggle { display:flex; border:1px solid #2d3348; border-radius:7px; overflow:hidden; }
  .dir-btn { background:none; border:none; color:#8899bb; padding:.35rem .9rem; font-size:.82rem; font-weight:600; cursor:pointer; transition:background .12s,color .12s; }
  .dir-btn.active-long  { background:#14532d; color:#4ade80; }
  .dir-btn.active-short { background:#7f1d1d; color:#f87171; }

  .podium-card.short-rank-1 { border-color:#ef4444; box-shadow:0 0 22px rgba(239,68,68,.13); }
  .podium-card.short-rank-2 { border-color:#f97316; }
  .podium-card.short-rank-3 { border-color:#eab308; }
  .short-rank-1 .podium-ticker { color:#ef4444; }
  .short-rank-2 .podium-ticker { color:#f97316; }
  .short-rank-3 .podium-ticker { color:#eab308; }
  .short-rank-1 .score-bar-fill { background:#ef4444; }
  .short-rank-2 .score-bar-fill { background:#f97316; }
  .short-rank-3 .score-bar-fill { background:#eab308; }

  .podium-card.mt-rank-1 { border-color:#06b6d4; box-shadow:0 0 22px rgba(6,182,212,.13); }
  .podium-card.mt-rank-2 { border-color:#0891b2; }
  .podium-card.mt-rank-3 { border-color:#0e7490; }
  .mt-rank-1 .podium-ticker { color:#22d3ee; }
  .mt-rank-2 .podium-ticker { color:#67e8f9; }
  .mt-rank-3 .podium-ticker { color:#a5f3fc; }
  .mt-rank-1 .score-bar-fill { background:#06b6d4; }
  .mt-rank-2 .score-bar-fill { background:#0891b2; }
  .mt-rank-3 .score-bar-fill { background:#0e7490; }
  .lb-bar-fill.midterm { background:#06b6d4; }
  .dir-btn.active-midterm { background:#164e63; color:#22d3ee; }

  .vol-low  { color:#4ade80; }
  .vol-med  { color:#fbbf24; }
  .vol-high { color:#f87171; }

  .risk-badge {
    display:inline-block; padding:.11rem .42rem; border-radius:4px;
    font-size:.62rem; font-weight:700; letter-spacing:.05em; white-space:nowrap;
  }
  .risk-low  { background:#0c2120; color:#34d399; border:1px solid #065f46; }
  .risk-med  { background:#1c1708; color:#fbbf24; border:1px solid #78350f; }
  .risk-high { background:#1a0c0c; color:#f87171; border:1px solid #7f1d1d; }

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
  <span class="tagline">Signal-driven research system</span>
</header>

<div class="tabs">
  <button class="tab-btn active" onclick="switchTab('brief', this)">Daily Brief</button>
  <button class="tab-btn" onclick="switchTab('top10', this)">Top 10</button>
  <button class="tab-btn" onclick="switchTab('editor', this)">Wiki Editor</button>
  <button class="tab-btn" onclick="switchTab('howto', this)">How It Works</button>
</div>

<!-- ═══════════════════════ DAILY BRIEF TAB -->
<div class="tab-panel active" id="tab-brief">
  <div class="card">
    <div class="card-title">
      Signal Research State
      <span class="actions">
        <button class="secondary" style="font-size:.7rem;padding:.25rem .5rem" onclick="loadBrief()">↻ Refresh</button>
      </span>
    </div>
    <div class="brief-meta" id="brief-meta"></div>
    <div class="brief-grid" id="brief-grid">
      <p class="state-msg">Loading…</p>
    </div>
  </div>
</div>

<!-- ═══════════════════════ TOP 10 TAB -->
<div class="tab-panel" id="tab-top10">
  <div class="card" style="padding:.7rem 1.1rem;margin-bottom:.75rem">
    <div class="filter-bar">
      <div class="filter-group">
        <label class="filter-label">Signals</label>
        <select id="t10-signal" class="filter-sel" onchange="loadTop10()">
          <option value="validated">Validated only (p &lt; 0.05)</option>
          <option value="borderline">Validated + borderline (p &lt; 0.10)</option>
          <option value="all">All signals</option>
        </select>
      </div>
      <div class="filter-group">
        <label class="filter-label">Sector</label>
        <select id="t10-sector" class="filter-sel" onchange="loadTop10()">
          <option value="all">All sectors</option>
          <option value="ai_infra">AI Infrastructure</option>
          <option value="space_defense">Space &amp; Defense</option>
          <option value="telecom">Telecom</option>
        </select>
      </div>
      <div class="filter-group">
        <label class="filter-label">Rank by</label>
        <select id="t10-score" class="filter-sel" onchange="loadTop10()">
          <option value="composite">Composite (alpha &times; hit rate &times; volume)</option>
          <option value="alpha">Avg alpha vs sector</option>
          <option value="hitrate">Hit rate</option>
        </select>
      </div>
      <div class="filter-group">
        <label class="filter-label">Direction</label>
        <div class="dir-toggle">
          <button id="dir-long"    class="dir-btn active-long"  onclick="setDirection('long')">▲ Long</button>
          <button id="dir-midterm" class="dir-btn"              onclick="setDirection('midterm')">📈 Mid-term</button>
          <button id="dir-short"   class="dir-btn"              onclick="setDirection('short')">▼ Short</button>
        </div>
      </div>
      <button class="secondary" style="font-size:.7rem;padding:.3rem .6rem;align-self:flex-end;margin-top:.2rem" onclick="loadTop10()">↻ Refresh</button>
    </div>
  </div>
  <div class="podium-grid" id="t10-podium">
    <p class="state-msg" style="grid-column:1/-1">Loading…</p>
  </div>
  <div class="card" id="t10-board">
    <div class="card-title">Leaderboard</div>
    <p class="state-msg">Loading…</p>
  </div>
</div>

<!-- ═══════════════════════ HOW IT WORKS TAB -->
<div class="tab-panel" id="tab-howto">
<div class="card howto-wrap">

  <div class="howto-section">
    <div class="howto-h2">What is SignalAlpha?</div>
    <p class="howto-p">SignalAlpha is a systematic signal research system. It detects recurring patterns in price volume and corporate event data, backtests each pattern against historical returns, and statistically validates whether the pattern produces alpha above the relevant sector ETF. Only patterns that clear a strict statistical bar (p&nbsp;&lt;&nbsp;0.05) are considered validated.</p>
    <p class="howto-p">The universe covers 68 public companies across three sectors: AI Infrastructure, Space &amp; Defense, and Telecom.</p>
  </div>

  <div class="howto-section">
    <div class="howto-h2">The Pipeline</div>
    <div class="pipeline">
      <div class="pipe-step"><strong>1 — Detect</strong><span>Scan price / volume / SEC filing data for candidate events</span></div>
      <span class="pipe-arrow">→</span>
      <div class="pipe-step"><strong>2 — Backtest</strong><span>Entry T+1 open, hold N days, exit at open. 10 bps slippage.</span></div>
      <span class="pipe-arrow">→</span>
      <div class="pipe-step"><strong>3 — Validate</strong><span>Paired t-test: stock return vs sector ETF over same window</span></div>
      <span class="pipe-arrow">→</span>
      <div class="pipe-step"><strong>4 — Holdout</strong><span>One-time out-of-sample test on reserved 2025+ data</span></div>
    </div>
  </div>

  <div class="howto-section">
    <div class="howto-h2">Key Metrics</div>
    <div class="metric-grid">

      <div class="metric-card">
        <div class="metric-name">Alpha vs Sector</div>
        <div class="metric-abbr">stock_return − sector_ETF_return</div>
        <div class="metric-desc">How much the stock outperformed (or underperformed) its sector ETF over the hold period. A positive alpha means the signal identifies idiosyncratic edge above the sector move. The sector benchmarks are SOXX (ai_infra), ITA (space_defense), and IYZ (telecom).</div>
        <span class="metric-good">+1.5% = strong edge</span>
      </div>

      <div class="metric-card">
        <div class="metric-name">Hit Rate</div>
        <div class="metric-abbr">wins / total_events</div>
        <div class="metric-desc">Percentage of signal firings that closed with a positive net return. A random strategy expects ~50%. Hit rate above 55% combined with positive alpha is a strong reliability indicator. For short candidates, the inverse applies — a low hit rate is desirable.</div>
        <span class="metric-good">&gt;55% long</span>
        <span class="metric-bad" style="margin-left:.5rem">&lt;45% short</span>
      </div>

      <div class="metric-card">
        <div class="metric-name">Avg Return</div>
        <div class="metric-abbr">mean(net_return)</div>
        <div class="metric-desc">Mean net return across all signal firings after deducting 10 bps round-trip slippage. Includes both winners and losers. This is the raw P&amp;L per trade — compare it against alpha to understand how much of the return is idiosyncratic vs sector-driven.</div>
        <span class="metric-good">+3% over 15d = strong</span>
      </div>

      <div class="metric-card">
        <div class="metric-name">p-value</div>
        <div class="metric-abbr">paired t-test(stock, sector)</div>
        <div class="metric-desc">Statistical significance of the alpha. A paired t-test compares stock returns vs sector ETF returns for identical entry/exit dates. p&nbsp;&lt;&nbsp;0.05 means there is less than a 5% chance the observed alpha is random. This is the primary validation gate.</div>
        <span class="metric-good">&lt;0.05 = validated</span>
        <span class="metric-bad" style="margin-left:.5rem">&gt;0.10 = graveyard</span>
      </div>

      <div class="metric-card">
        <div class="metric-name">Sharpe (annualized)</div>
        <div class="metric-abbr">mean / std × √(252 / hold_days)</div>
        <div class="metric-desc">Risk-adjusted return. Divides mean return by its standard deviation and scales to annual frequency. A Sharpe above 0.5 is good for a signal strategy; above 1.0 is excellent. The volume anomaly at 15d hold produces Sharpe 1.22 in the holdout period.</div>
        <span class="metric-good">&gt;0.5 good  &gt;1.0 excellent</span>
      </div>

      <div class="metric-card">
        <div class="metric-name">Composite Score</div>
        <div class="metric-abbr">alpha × hit_rate × log(1 + N)</div>
        <div class="metric-desc">The Long ranking metric. Rewards signals with high alpha AND consistent winning AND enough historical observations to trust. A signal with great alpha but only 5 events scores lower than one with moderate alpha across 200 events.</div>
        <span class="metric-good">Higher = better ranked</span>
      </div>

      <div class="metric-card">
        <div class="metric-name">Risk Level</div>
        <div class="metric-abbr">std(net_return) per stock</div>
        <div class="metric-desc">Volatility of net returns across all signal firings for that stock. Used to classify investment risk and power the Mid-term ranking.</div>
        <span class="metric-good" style="display:block">🟢 LOW &lt;10% std</span>
        <span class="metric-bad" style="color:#fbbf24;display:block">🟡 MED 10–20%</span>
        <span class="metric-bad" style="display:block">🔴 HIGH &gt;20%</span>
      </div>

    </div>
  </div>

  <div class="howto-section">
    <div class="howto-h2">Signals</div>
    <div class="signal-list">
      <div class="signal-item">
        <div class="signal-item-name">Volume Anomaly ×2.0 — 15d Hold &nbsp;<span class="status-pill pill-validated">validated</span></div>
        <div class="signal-item-desc">Fires when a ticker's 5-day average volume exceeds 2× its 60-day median volume. Debounced to one firing per ticker per 5 trading days. Entry at T+1 open, exit 15 trading days later. In-sample p=0.0046 across 1,480 events (2018–2024). Holdout alpha +1.58%, Sharpe 1.22 (2025–2026). The only currently validated signal.</div>
      </div>
      <div class="signal-item">
        <div class="signal-item-name">8-K Filing — Excluding Earnings &nbsp;<span class="status-pill pill-borderline">borderline</span></div>
        <div class="signal-item-desc">Fires on any non-earnings 8-K SEC filing. In-sample p=0.053 at 30d hold. Holdout p=0.27 — does not confirm out-of-sample. Currently in the graveyard for production use. Further filtering by 8-K item type or sector may be needed.</div>
      </div>
    </div>
  </div>

  <div class="howto-section">
    <div class="howto-h2">Long vs Short Rankings</div>
    <div class="dir-explainer">
      <div class="dir-card dir-card-long">
        <div class="dir-card-title">▲ Long — Top 10</div>
        <p>Stocks where the signal consistently fires before price appreciation above the sector ETF. Ranked by <b>composite score</b> = alpha × hit_rate × log(N). Candidates to buy when the volume anomaly fires. Each stock shows a <b>risk badge</b> (LOW / MED / HIGH) based on return volatility.</p>
      </div>
      <div class="dir-card" style="background:#0b1a1f;border:1px solid #0e7490;border-radius:9px;padding:1rem">
        <div class="dir-card-title" style="color:#22d3ee">📈 Mid-term — 1 to 3 Months</div>
        <p style="font-size:.76rem;color:#8899bb;line-height:1.65">Stocks with positive alpha and low volatility — suitable for patient 1–3 month holds. Ranked by <b>Information Ratio score</b> = (alpha / volatility) × hit_rate × log(N). High-volatility names score low even with great alpha. Look for <span style="color:#34d399;font-weight:700">LOW RISK</span> badges.</p>
      </div>
      <div class="dir-card dir-card-short">
        <div class="dir-card-title">▼ Short — Top 10</div>
        <p>Stocks where the signal fires before underperformance vs sector ETF. Ranked by <b>short score</b> = |alpha| × (1 − hit_rate) × log(N). Volume spikes here are distribution events, not accumulation. Short Win Rate = probability the position profits when shorted.</p>
      </div>
    </div>
  </div>

  <div class="howto-section">
    <div class="howto-h2">Statistical Guardrails</div>
    <p class="howto-p"><b>Minimum N = 30 events</b> to report any result. Signals with fewer events are inconclusive regardless of p-value.</p>
    <p class="howto-p"><b>Holdout window:</b> all data from 2025-01-01 onward was never seen during parameter development. The holdout was run once, results are final, and they are not used to tune parameters.</p>
    <p class="howto-p"><b>Slippage:</b> 10 bps round-trip is deducted from every trade to model realistic execution costs.</p>
    <p class="howto-p"><b>No look-ahead:</b> all signals use only data available at signal-fire time. Rolling windows are right-aligned at T; entry is T+1 open.</p>
  </div>

</div>
</div>

<!-- ═══════════════════════ WIKI EDITOR TAB -->
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
        <p style="font-size:.75rem;color:#8899bb;margin-bottom:.6rem">Scaffold missing pages and refresh AUTOGEN sections from DB.</p>
        <button class="success" onclick="runAutogen()" id="autogenBtn">Run Autogen</button>
        <div id="autogen-out" style="margin-top:.6rem;font-size:.75rem;color:#94a3b8;white-space:pre-wrap"></div>
      </div>
    </div>

    <!-- Right: editor + result -->
    <div>
      <div class="card">
        <div class="card-title">Editor <span id="editing-label" style="color:#6366f1;font-size:.75rem;margin-left:.5rem"></span></div>
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
const _tabLoaded = {};
function switchTab(name, btn) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('tab-' + name).classList.add('active');
  if (name === 'top10' && !_tabLoaded.top10) { _tabLoaded.top10 = true; loadTop10(); }
}

let _t10Direction = 'long';
function setDirection(dir) {
  _t10Direction = dir;
  document.getElementById('dir-long').className    = 'dir-btn' + (dir === 'long'    ? ' active-long'    : '');
  document.getElementById('dir-midterm').className = 'dir-btn' + (dir === 'midterm' ? ' active-midterm' : '');
  document.getElementById('dir-short').className   = 'dir-btn' + (dir === 'short'   ? ' active-short'   : '');
  loadTop10();
}

// ── Toast ─────────────────────────────────────────────────────────────────────
function toast(msg, ms=2500) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), ms);
}

// ── Daily Brief ───────────────────────────────────────────────────────────────
async function loadBrief() {
  document.getElementById('brief-meta').textContent = '';
  document.getElementById('brief-grid').innerHTML = '<p class="state-msg">Loading…</p>';
  try {
    const data = await (await fetch('/brief')).json();
    renderBrief(data);
  } catch(e) {
    document.getElementById('brief-grid').innerHTML =
      '<p class="state-msg" style="color:#f87171">Error: ' + escHtml(e.message) + '</p>';
  }
}

function renderBrief(data) {
  const signals = data.signals || [];
  document.getElementById('brief-meta').innerHTML =
    `As of <b>${escHtml(data.generated_at)}</b> &mdash; ${signals.length} signal${signals.length!==1?'s':''} tracked`;

  if (!signals.length) {
    document.getElementById('brief-grid').innerHTML =
      '<p class="state-msg">No signal runs found. Run a backtest to populate signal_runs.</p>';
    return;
  }

  const pct = v => v === null || v === undefined ? '<span class="neu">—</span>'
    : `<span class="${v>=0?'pos':'neg'}">${v>=0?'+':''}${(v*100).toFixed(1)}%</span>`;
  const pval = v => v === null || v === undefined ? '<span class="neu">—</span>'
    : `<span class="${v<0.05?'pos':v<0.10?'amber':'neu'}">${v.toFixed(4)}</span>`;
  const num = (v, d=2) => v === null || v === undefined ? '<span class="neu">—</span>'
    : `<span class="neu">${v.toFixed(d)}</span>`;

  const html = signals.map(s => {
    const statusCls = 'pill-' + s.status;
    const ctxCls   = 'ctx-' + s.context_status;
    const ctxIcon  = s.context_status === 'current' ? '●' : s.context_status === 'stale' ? '◑' : '○';
    const wikiBtn = s.wiki_path
      ? `<button class="wiki-link" onclick="event.stopPropagation();openWikiPage('${escAttr(s.wiki_path)}')">wiki →</button>`
      : `<span style="font-size:.68rem;color:#374151">no wiki</span>`;

    return `<div class="signal-card" id="sc-${s.run_id}" onclick="toggleDrilldown(${s.run_id}, event)">
      <div>
        <div class="sc-name">${escHtml(s.display_name || s.signal_id)}</div>
        <div class="sc-meta">${escHtml(s.signal_id)} &middot; run #${s.run_id} &middot; ${s.n_events ?? '?'} events &middot; ${s.hold_days}d hold</div>
        ${s.event_window_start ? `<div class="sc-meta">${s.event_window_start} → ${s.event_window_end}</div>` : ''}
      </div>
      <div class="sc-stats">
        <div class="stat-item"><span class="stat-label">Hit rate</span><span class="stat-val">${pct(s.hit_rate)}</span></div>
        <div class="stat-item"><span class="stat-label">Return</span><span class="stat-val">${pct(s.mean_return)}</span></div>
        <div class="stat-item"><span class="stat-label">Alpha</span><span class="stat-val">${pct(s.mean_alpha_sector)}</span></div>
        <div class="stat-item"><span class="stat-label">p-value</span><span class="stat-val">${pval(s.p_value_vs_sector)}</span></div>
        <div class="stat-item"><span class="stat-label">Sharpe</span><span class="stat-val">${num(s.sharpe_ann)}</span></div>
      </div>
      <div class="sc-right">
        <span class="status-pill ${statusCls}">${s.status}</span>
        <span class="ctx-pill ${ctxCls}">${ctxIcon} ${s.context_status}</span>
        ${wikiBtn}
      </div>
      <div class="drilldown" id="dd-${s.run_id}" style="grid-column:1/-1">
        <div class="drilldown-hdr">Per-event breakdown <span id="dd-count-${s.run_id}" style="color:#94a3b8;font-size:.7rem"></span></div>
        <div id="dd-body-${s.run_id}"><p class="ev-loading">Loading…</p></div>
      </div>
    </div>`;
  }).join('');

  document.getElementById('brief-grid').innerHTML = html;
}

const _ddLoaded = new Set();

async function toggleDrilldown(runId, ev) {
  if (ev.target.classList.contains('wiki-link')) return;
  const dd = document.getElementById('dd-' + runId);
  if (!dd) return;
  const isOpen = dd.classList.contains('open');
  if (isOpen) { dd.classList.remove('open'); return; }
  dd.classList.add('open');
  if (_ddLoaded.has(runId)) return;
  _ddLoaded.add(runId);
  try {
    const data = await (await fetch('/events?run_id=' + runId)).json();
    const events = data.events || [];
    document.getElementById('dd-count-' + runId).textContent = `(${events.length} events)`;
    if (!events.length) {
      document.getElementById('dd-body-' + runId).innerHTML = '<p class="ev-loading">No events found.</p>';
      return;
    }
    const pct = v => v === null ? '—' : `${v>=0?'+':''}${(v*100).toFixed(1)}%`;
    const cls = v => v === null ? 'neu' : v >= 0 ? 'pos' : 'neg';
    const avg = arr => arr.length ? arr.reduce((a,b)=>a+b,0)/arr.length : null;

    // Group by sector
    const bySector = {};
    events.forEach(e => {
      const sec = e.sector || 'unknown';
      if (!bySector[sec]) bySector[sec] = [];
      bySector[sec].push(e);
    });

    let html = '';
    for (const [sector, evs] of Object.entries(bySector)) {
      const returns = evs.map(e=>e.net_return).filter(v=>v!==null);
      const alphas  = evs.map(e=>e.alpha_sector).filter(v=>v!==null);
      const hits    = returns.filter(v=>v>0).length;
      const secAvgRet = avg(returns), secAvgAlpha = avg(alphas);

      html += `<div style="margin-bottom:.9rem">
        <div style="display:flex;align-items:center;gap:.8rem;margin-bottom:.35rem;padding:.3rem .5rem;background:#1a1d2a;border-radius:5px">
          <span style="font-size:.72rem;font-weight:700;color:#a5b4fc;text-transform:uppercase;letter-spacing:.05em">${escHtml(sector)}</span>
          <span style="font-size:.7rem;color:#7a8aaa">${evs.length} events</span>
          <span style="font-size:.7rem;color:#7a8aaa">hit rate <span class="${cls(secAvgRet)}">${returns.length?Math.round(hits/returns.length*100)+'%':'—'}</span></span>
          <span style="font-size:.7rem;color:#7a8aaa">avg return <span class="${cls(secAvgRet)}">${pct(secAvgRet)}</span></span>
          <span style="font-size:.7rem;color:#7a8aaa">avg alpha <span class="${cls(secAvgAlpha)}">${pct(secAvgAlpha)}</span></span>
        </div>
        <table class="ev-tbl" style="margin-bottom:.2rem">
          <thead><tr>
            <th>Ticker</th><th>Name</th><th>Event date</th><th>Return</th><th>Alpha</th>
          </tr></thead>
          <tbody>`;

      evs.slice(0, 30).forEach(e => {
        html += `<tr>
          <td><button class="wiki-link" style="font-weight:700;font-size:.78rem" onclick="openWikiPage('wiki/companies/public/${escAttr(e.ticker)}.md')">${escHtml(e.ticker)}</button></td>
          <td style="color:#7a8aaa;font-size:.72rem">${escHtml(e.name ?? '—')}</td>
          <td class="td-mono">${e.event_date ?? '—'}</td>
          <td><span class="${cls(e.net_return)}">${pct(e.net_return)}</span></td>
          <td><span class="${cls(e.alpha_sector)}">${pct(e.alpha_sector)}</span></td>
        </tr>`;
      });
      if (evs.length > 30) html += `<tr><td colspan="5" style="color:#7a8aaa;font-size:.68rem;padding:.3rem .5rem">…and ${evs.length-30} more</td></tr>`;
      html += `</tbody></table></div>`;
    }

    document.getElementById('dd-body-' + runId).innerHTML = `<div style="overflow-x:auto">${html}</div>`;
  } catch(e) {
    document.getElementById('dd-body-' + runId).innerHTML = `<p class="ev-loading" style="color:#f87171">Error: ${escHtml(e.message)}</p>`;
  }
}

function openWikiPage(path) {
  if (!path) { toast('No wiki page yet — run Autogen first.'); return; }
  const editorBtn = document.querySelectorAll('.tab-btn')[1];
  switchTab('editor', editorBtn);
  fetch('/wiki-pages').then(r => r.json()).then(data => {
    renderPages(data.pages);
    setTimeout(() => {
      const el = document.querySelector(`.page-item[data-path="${escAttr(path)}"]`);
      if (el) loadPage(el, path);
    }, 50);
  });
}

// ── Page browser ──────────────────────────────────────────────────────────────
let _activePage = null;

async function loadPages(pages) {
  const el = document.getElementById('page-list');
  if (!pages) {
    el.innerHTML = '<p class="no-pages">Loading…</p>';
    try { pages = (await (await fetch('/wiki-pages')).json()).pages; }
    catch(e) { el.innerHTML = '<p class="no-pages">Error.</p>'; return; }
  }
  renderPages(pages);
}

function renderPages(pages) {
  const el = document.getElementById('page-list');
  if (!pages.length) { el.innerHTML = '<p class="no-pages">No wiki pages — run Autogen.</p>'; return; }
  const byGroup = {};
  pages.forEach(p => { (byGroup[p.group] = byGroup[p.group] || []).push(p); });
  const labels = { 'signals':'Signals','companies/public':'Companies (public)',
                   'companies/private':'Companies (private)','sectors':'Sectors' };
  let html = '';
  for (const [group, items] of Object.entries(byGroup)) {
    html += `<div class="page-group-label">${labels[group]||group}</div>`;
    items.forEach(p => {
      html += `<div class="page-item" data-path="${escAttr(p.path)}" onclick="loadPage(this,'${escAttr(p.path)}')">${escHtml(p.name)}</div>`;
    });
  }
  el.innerHTML = html;
  if (_activePage)
    document.querySelectorAll('.page-item').forEach(e => {
      if (e.dataset.path === _activePage) e.classList.add('active');
    });
}

async function loadPage(el, path) {
  document.querySelectorAll('.page-item').forEach(x => x.classList.remove('active'));
  el.classList.add('active');
  _activePage = path;
  try {
    const data = await (await fetch('/wiki-page-content?path=' + encodeURIComponent(path))).json();
    document.getElementById('content').value = data.content;
    document.getElementById('filename').textContent = path.split('/').pop();
    document.getElementById('editing-label').textContent = path.split('/').pop();
    document.getElementById('result').style.display = 'none';
  } catch(e) { toast('Failed to load page.'); }
}

// ── File picker ───────────────────────────────────────────────────────────────
document.getElementById('fileInput').addEventListener('change', e => {
  const file = e.target.files[0]; if (!file) return;
  document.getElementById('filename').textContent = file.name;
  document.getElementById('editing-label').textContent = file.name;
  const reader = new FileReader();
  reader.onload = ev => document.getElementById('content').value = ev.target.result;
  reader.readAsText(file);
});

// ── Validate ──────────────────────────────────────────────────────────────────
async function runValidate() {
  const content = document.getElementById('content').value.trim();
  if (!content) { alert('Load a wiki page first.'); return; }
  const btn = document.getElementById('runBtn');
  const spinner = document.getElementById('spinner');
  btn.disabled = true; spinner.style.display = 'block';
  document.getElementById('result').style.display = 'none';
  try {
    const fd = new FormData(); fd.append('content', content);
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
    statBox(data.failures.length, 'failure') +
    statBox(data.warnings.length, 'warning') +
    statBox(data.pass_results.length, 'pass', 'es run');
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

// ── Top 10 ────────────────────────────────────────────────────────────────────
async function loadTop10() {
  const sig   = document.getElementById('t10-signal').value;
  const sec   = document.getElementById('t10-sector').value;
  const score = document.getElementById('t10-score').value;
  const dir   = _t10Direction;
  document.getElementById('t10-podium').innerHTML =
    '<p class="state-msg" style="grid-column:1/-1">Loading…</p>';
  document.getElementById('t10-board').innerHTML =
    '<div class="card-title">Leaderboard</div><p class="state-msg">Loading…</p>';
  try {
    const p = new URLSearchParams({ signal_filter: sig, sector: sec, score_by: score, direction: dir, limit: 10 });
    const data = await (await fetch('/top10?' + p)).json();
    renderTop10(data);
  } catch(e) {
    document.getElementById('t10-podium').innerHTML = '';
    document.getElementById('t10-board').innerHTML =
      '<div class="card-title">Leaderboard</div><p class="state-msg" style="color:#f87171">Error: ' +
      escHtml(e.message) + '</p>';
  }
}

function renderTop10(data) {
  const stocks    = data.stocks || [];
  const isShort   = data.direction === 'short';
  const isMidterm = data.direction === 'midterm';
  const scoreKey  = isShort ? 'short_score' : isMidterm ? 'midterm_score' : (data.score_by || 'composite_score');
  const maxScore  = stocks.length && stocks[0][scoreKey] ? stocks[0][scoreKey] : 1;

  const pct = v => v === null || v === undefined ? '—'
    : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(1)}%`;
  const cls = v => v === null || v === undefined ? 'neu' : v >= 0 ? 'pos' : 'neg';

  const SECTOR_LABELS = { ai_infra:'AI Infra', space_defense:'Space & Defense', telecom:'Telecom' };
  function sectorBadge(s) {
    return `<span class="sector-badge sec-${escAttr(s||'unknown')}">${escHtml(SECTOR_LABELS[s]||s||'—')}</span>`;
  }
  function riskBadge(std) {
    if (std === null || std === undefined) return '';
    const cls   = std < 0.10 ? 'risk-low' : std < 0.20 ? 'risk-med' : 'risk-high';
    const label = std < 0.10 ? 'LOW RISK' : std < 0.20 ? 'MED RISK' : 'HIGH RISK';
    return `<span class="risk-badge ${cls}">${label}</span>`;
  }

  const LONG_MEDALS    = ['🥇','🥈','🥉'];
  const SHORT_MEDALS   = ['📉','📉','📉'];
  const MIDTERM_MEDALS = ['🏅','🏅','🏅'];
  const LONG_RANK_CLS    = ['rank-1','rank-2','rank-3'];
  const SHORT_RANK_CLS   = ['short-rank-1','short-rank-2','short-rank-3'];
  const MIDTERM_RANK_CLS = ['mt-rank-1','mt-rank-2','mt-rank-3'];
  const MEDALS   = isShort ? SHORT_MEDALS   : isMidterm ? MIDTERM_MEDALS : LONG_MEDALS;
  const RANK_CLS = isShort ? SHORT_RANK_CLS : isMidterm ? MIDTERM_RANK_CLS : LONG_RANK_CLS;

  // ── Podium (top 3) ──────────────────────────────────────────────────────────
  const podiumEl = document.getElementById('t10-podium');
  const emptyMsg = isShort   ? 'No short candidates found — try relaxing the signal filter.'
    : isMidterm ? 'No mid-term candidates found — try relaxing the signal filter.'
    : 'No stocks matched — try relaxing the signal filter.';

  if (!stocks.length) {
    podiumEl.innerHTML = `<p class="state-msg" style="grid-column:1/-1">${emptyMsg}</p>`;
    document.getElementById('t10-board').innerHTML = '<div class="card-title">Leaderboard</div>';
    return;
  }

  podiumEl.innerHTML = stocks.slice(0, 3).map((s, i) => {
    const score      = s[scoreKey] ?? 0;
    const barPct     = maxScore > 0 ? (score / maxScore * 100).toFixed(1) : 0;
    const wiki       = `wiki/companies/public/${s.ticker}.md`;

    // Labels and values vary by direction
    const hrVal    = isShort ? (s.hit_rate !== null ? 1 - s.hit_rate : null) : s.hit_rate;
    const hrDisp   = hrVal !== null ? Math.round(hrVal * 100) + '%' : '—';
    const hrCls    = hrVal !== null ? (hrVal >= 0.5 ? 'pos' : 'neg') : 'neu';
    const hrLabel  = isShort ? 'Short win rate' : 'Hit rate';
    const alphaLabel = isShort ? 'Alpha (short ↓)' : 'Alpha';

    // Volatility display for mid-term
    const volPct  = s.std_return !== null ? Math.round(s.std_return * 100) + '%' : '—';
    const volCls  = s.std_return === null ? 'neu'
      : s.std_return < 0.10 ? 'vol-low' : s.std_return < 0.20 ? 'vol-med' : 'vol-high';

    const extraStat = isMidterm
      ? `<div class="stat-item"><span class="stat-label">Volatility</span><span class="stat-val ${volCls}">${volPct}</span></div>`
      : `<div class="stat-item"><span class="stat-label">Avg return</span><span class="stat-val ${cls(s.avg_return)}">${pct(s.avg_return)}</span></div>`;

    return `
    <div class="podium-card ${RANK_CLS[i]}">
      <div class="podium-medal">${MEDALS[i]}</div>
      <div class="podium-ticker">${escHtml(s.ticker)}</div>
      <div class="podium-company">${escHtml(s.name || '')}</div>
      <div style="display:flex;gap:.35rem;flex-wrap:wrap;align-items:center">${sectorBadge(s.sector)}${riskBadge(s.std_return)}</div>
      <div class="podium-stats">
        <div class="stat-item"><span class="stat-label">Signals</span><span class="stat-val neu">${s.n_signals}</span></div>
        <div class="stat-item"><span class="stat-label">${alphaLabel}</span><span class="stat-val ${cls(s.avg_alpha)}">${pct(s.avg_alpha)}</span></div>
        <div class="stat-item"><span class="stat-label">${hrLabel}</span><span class="stat-val ${hrCls}">${hrDisp}</span></div>
        ${extraStat}
        <div class="stat-item"><span class="stat-label">Last signal</span><span class="stat-val neu" style="font-size:.72rem">${s.last_signal || '—'}</span></div>
      </div>
      <div class="score-bar-wrap">
        <div class="score-bar-fill" style="width:${barPct}%"></div>
      </div>
      <button class="wiki-link" style="margin-top:.45rem;font-size:.76rem"
        onclick="openWikiPage('${escAttr(wiki)}')">View company wiki →</button>
    </div>`;
  }).join('');

  // ── Leaderboard (#4–10) ─────────────────────────────────────────────────────
  const rest    = stocks.slice(3);
  const boardEl = document.getElementById('t10-board');
  const boardTitle = isShort   ? `Short Candidates — #4 to #${stocks.length}`
    : isMidterm ? `Mid-term (1–3 months, lower risk) — #4 to #${stocks.length}`
    : `Leaderboard — #4 to #${stocks.length}`;

  if (!rest.length) {
    boardEl.innerHTML = `<div class="card-title">${boardTitle}</div>` +
      '<p class="state-msg">Only ' + stocks.length + ' stock(s) matched the current filters.</p>';
    return;
  }

  const alphaHdr = isShort   ? 'Alpha (↓ below sector)'
    : isMidterm ? 'Alpha vs Sector' : 'Avg Alpha';
  const hrHdr   = isShort   ? 'Short Win Rate'
    : isMidterm ? 'Hit Rate' : 'Hit Rate';
  const retHdr  = isMidterm ? 'Volatility' : 'Avg Return';
  const barClass = isShort ? 'lb-bar-fill short' : isMidterm ? 'lb-bar-fill midterm' : 'lb-bar-fill';

  let html = `<div class="card-title">${boardTitle}</div>
    <div style="overflow-x:auto"><table class="lb-tbl"><thead><tr>
      <th class="lb-rank">#</th>
      <th>Ticker</th><th>Company</th><th>Sector</th>
      <th>Signals</th><th>${alphaHdr}</th><th>${hrHdr}</th><th>${retHdr}</th>
      <th>Last Signal</th><th class="lb-bar-cell">Score</th>
    </tr></thead><tbody>`;

  rest.forEach((s, i) => {
    const score   = s[scoreKey] ?? 0;
    const barPct  = maxScore > 0 ? (score / maxScore * 100).toFixed(1) : 0;
    const hrVal   = isShort ? (s.hit_rate !== null ? 1 - s.hit_rate : null) : s.hit_rate;
    const hrDisp  = hrVal !== null ? Math.round(hrVal * 100) + '%' : '—';
    const hrCls   = hrVal !== null ? (hrVal >= 0.5 ? 'pos' : 'neg') : 'neu';
    const wiki    = `wiki/companies/public/${s.ticker}.md`;
    // Mid-term: show volatility instead of avg return
    const retVal  = isMidterm
      ? `<span class="${s.std_return === null ? 'neu' : s.std_return < 0.10 ? 'vol-low' : s.std_return < 0.20 ? 'vol-med' : 'vol-high'}">${s.std_return !== null ? Math.round(s.std_return * 100) + '%' : '—'}</span>`
      : `<span class="${cls(s.avg_return)}">${pct(s.avg_return)}</span>`;
    html += `<tr onclick="openWikiPage('${escAttr(wiki)}')">
      <td class="lb-rank">${i + 4}</td>
      <td class="lb-ticker-cell">${escHtml(s.ticker)} ${riskBadge(s.std_return)}</td>
      <td style="color:#8899bb;font-size:.75rem">${escHtml(s.name || '—')}</td>
      <td>${sectorBadge(s.sector)}</td>
      <td class="neu">${s.n_signals}</td>
      <td><span class="${cls(s.avg_alpha)}">${pct(s.avg_alpha)}</span></td>
      <td><span class="${hrCls}">${hrDisp}</span></td>
      <td>${retVal}</td>
      <td class="neu" style="font-size:.73rem">${s.last_signal || '—'}</td>
      <td class="lb-bar-cell">
        <div class="lb-bar"><div class="${barClass}" style="width:${barPct}%"></div></div>
      </td>
    </tr>`;
  });
  html += '</tbody></table></div>';
  boardEl.innerHTML = html;
}

// ── Autogen ───────────────────────────────────────────────────────────────────
async function runAutogen() {
  const btn = document.getElementById('autogenBtn');
  const out = document.getElementById('autogen-out');
  btn.disabled = true; out.textContent = 'Running…';
  try {
    const data = await (await fetch('/autogen', {method:'POST'})).json();
    out.textContent = data.results.join('\n') || 'Nothing to update.';
    toast('Autogen done — ' + data.results.length + ' page(s) affected.');
    loadPages(); loadBrief();
  } catch(e) { out.textContent = 'Error: ' + e.message; }
  finally { btn.disabled = false; }
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function statBox(n, label, suffix='s') {
  return `<div class="stat-box"><b>${n}</b> ${label}${n!==1?suffix:''}</div>`;
}
function badge(cls, text) { return `<span class="badge ${cls}">${escHtml(String(text))}</span>`; }
function issueHTML(issue, kind) {
  return `<li class="issue ${kind}">` +
    `<div class="issue-rule">${escHtml(issue.rule)}</div>` +
    `<div class="issue-msg">${escHtml(issue.message)}</div>` +
    (issue.location ? `<div class="issue-loc">${escHtml(issue.location)}</div>` : '') +
    '</li>';
}
function toggle(h) { h.nextElementSibling.classList.toggle('open'); }
function escHtml(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function escAttr(s) { return String(s).replace(/'/g,"\\'").replace(/"/g,'&quot;'); }

// Boot
loadBrief();
loadPages();
</script>
</body>
</html>
"""


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    return _HTML


@app.get("/brief")
async def daily_brief():
    db = _open_db()
    try:
        return JSONResponse(build_daily_brief(db))
    finally:
        db.close()


@app.get("/events")
async def signal_events(run_id: int = Query(...)):
    db = _open_db()
    try:
        rows = db.execute("""
            SELECT se.ticker, se.event_date, se.entry_date, se.exit_date,
                   se.net_return, se.alpha_sector, se.alpha_spy, se.sector_benchmark,
                   u.sector, u.name
            FROM signal_events se
            LEFT JOIN universe u ON u.ticker = se.ticker
            WHERE se.run_id = ?
            ORDER BY u.sector NULLS LAST, se.net_return DESC
        """, [run_id]).fetchall()
        cols = ["ticker", "event_date", "entry_date", "exit_date",
                "net_return", "alpha_sector", "alpha_spy", "sector_benchmark",
                "sector", "name"]
        events = []
        for r in rows:
            d = dict(zip(cols, r))
            for k in ("event_date", "entry_date", "exit_date"):
                d[k] = str(d[k])[:10] if d[k] else None
            for k in ("net_return", "alpha_sector", "alpha_spy"):
                d[k] = round(float(d[k]), 6) if d[k] is not None else None
            events.append(d)
        return JSONResponse({"run_id": run_id, "events": events})
    finally:
        db.close()


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
        db = _open_db()
        try:
            result = validate(tmp_path, db)
        finally:
            db.close()
    finally:
        tmp_path.unlink(missing_ok=True)
    return JSONResponse(_to_dict(result))


@app.get("/top10")
async def top10_endpoint(
    signal_filter: str = Query("validated"),
    sector: str = Query("all"),
    score_by: str = Query("composite"),
    direction: str = Query("long"),
    limit: int = Query(10),
):
    VALID_FILTERS   = {"all", "validated", "borderline"}
    VALID_SECTORS   = {"all", "ai_infra", "space_defense", "telecom"}
    VALID_SCORE     = {"composite", "alpha", "hitrate"}
    VALID_DIRECTION = {"long", "short", "midterm"}
    if signal_filter not in VALID_FILTERS:
        signal_filter = "validated"
    if sector not in VALID_SECTORS:
        sector = "all"
    if score_by not in VALID_SCORE:
        score_by = "composite"
    if direction not in VALID_DIRECTION:
        direction = "long"

    sig_cond = (
        "AND sr.p_value_vs_sector < 0.05"      if signal_filter == "validated"
        else "AND sr.p_value_vs_sector < 0.10" if signal_filter == "borderline"
        else ""
    )
    sec_cond = f"AND u.sector = '{sector}'" if sector != "all" else ""

    if direction == "long":
        dir_having = ""
        order_col  = {"composite": "composite_score", "alpha": "avg_alpha", "hitrate": "hit_rate"}[score_by]
        order_dir  = "DESC"
    elif direction == "short":
        dir_having = "AND AVG(se.alpha_sector) < 0"
        order_col  = {"composite": "short_score", "alpha": "abs_alpha", "hitrate": "short_hit_rate"}[score_by]
        order_dir  = "DESC"
    else:  # midterm
        # Only positive-alpha stocks; score penalises volatility
        dir_having = "AND AVG(se.alpha_sector) > 0 AND STDDEV(se.net_return) > 0"
        order_col  = "midterm_score"
        order_dir  = "DESC"

    db = _open_db()
    try:
        rows = db.execute(f"""
            SELECT se.ticker, u.name, u.sector,
                   COUNT(*)                                                                    AS n_signals,
                   AVG(se.alpha_sector)                                                        AS avg_alpha,
                   AVG(se.net_return)                                                          AS avg_return,
                   STDDEV(se.net_return)                                                       AS std_return,
                   SUM(CASE WHEN se.net_return > 0 THEN 1.0 ELSE 0.0 END)
                     / NULLIF(COUNT(*), 0)                                                     AS hit_rate,
                   MAX(se.event_date)                                                          AS last_signal,
                   -- Long composite
                   AVG(se.alpha_sector)
                     * (SUM(CASE WHEN se.net_return > 0 THEN 1.0 ELSE 0.0 END)
                        / NULLIF(COUNT(*), 0))
                     * LN(COUNT(*) + 1)                                                        AS composite_score,
                   -- Short composite: |alpha| × (1 − hit_rate) × log(n+1)
                   ABS(AVG(se.alpha_sector))
                     * (1 - SUM(CASE WHEN se.net_return > 0 THEN 1.0 ELSE 0.0 END)
                              / NULLIF(COUNT(*), 0))
                     * LN(COUNT(*) + 1)                                                        AS short_score,
                   ABS(AVG(se.alpha_sector))                                                   AS abs_alpha,
                   1 - SUM(CASE WHEN se.net_return > 0 THEN 1.0 ELSE 0.0 END)
                         / NULLIF(COUNT(*), 0)                                                 AS short_hit_rate,
                   -- Mid-term score: (alpha / std) × hit_rate × log(n+1) — rewards risk-adjusted consistency
                   CASE WHEN STDDEV(se.net_return) > 0
                        THEN (AVG(se.alpha_sector) / STDDEV(se.net_return))
                               * (SUM(CASE WHEN se.net_return > 0 THEN 1.0 ELSE 0.0 END)
                                  / NULLIF(COUNT(*), 0))
                               * LN(COUNT(*) + 1)
                        ELSE 0 END                                                             AS midterm_score
            FROM signal_events se
            JOIN signal_runs sr ON sr.run_id = se.run_id
            JOIN universe    u  ON u.ticker  = se.ticker
            WHERE 1=1 {sig_cond} {sec_cond}
            GROUP BY se.ticker, u.name, u.sector
            HAVING COUNT(*) >= 5 {dir_having}
            ORDER BY {order_col} {order_dir} NULLS LAST
            LIMIT ?
        """, [limit]).fetchall()

        cols = ["ticker", "name", "sector", "n_signals",
                "avg_alpha", "avg_return", "std_return", "hit_rate", "last_signal",
                "composite_score", "short_score", "abs_alpha", "short_hit_rate", "midterm_score"]
        stocks = []
        for r in rows:
            d = dict(zip(cols, r))
            d["last_signal"] = str(d["last_signal"])[:10] if d["last_signal"] else None
            for k in ("avg_alpha", "avg_return", "std_return", "hit_rate",
                      "composite_score", "short_score", "abs_alpha", "short_hit_rate", "midterm_score"):
                d[k] = round(float(d[k]), 6) if d[k] is not None else None
            stocks.append(d)

        return JSONResponse({
            "score_by": order_col,
            "direction": direction,
            "signal_filter": signal_filter,
            "sector": sector,
            "stocks": stocks,
        })
    finally:
        db.close()


@app.post("/autogen")
async def autogen_endpoint():
    results = run_autogen()
    return JSONResponse({"results": results})


@app.post("/admin/ingest")
async def ingest_endpoint(background_tasks: BackgroundTasks, secret: str = Query(...)):
    """Trigger incremental price ingestion. Runs in background; returns immediately."""
    expected = os.environ.get("ADMIN_SECRET", "")
    if not expected or secret != expected:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    def _run():
        from signalalpha.ingest_prices import ingest_all
        ingest_all()

    background_tasks.add_task(_run)
    return JSONResponse({"ok": True, "status": "ingestion started in background"})


@app.post("/admin/restore-db")
async def restore_db(file: UploadFile, secret: str = Query(...)):
    """Upload a DuckDB snapshot to the volume. Requires ADMIN_SECRET env var."""
    expected = os.environ.get("ADMIN_SECRET", "")
    if not expected or secret != expected:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    data = await file.read()
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    DB_PATH.write_bytes(data)
    return JSONResponse({"ok": True, "bytes": len(data), "path": str(DB_PATH)})


if __name__ == "__main__":
    uvicorn.run("signalalpha.wiki.app:app", host="127.0.0.1", port=8000, reload=True)
