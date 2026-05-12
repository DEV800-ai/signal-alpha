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

from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

from signalalpha.wiki.admin import _open_db, router as admin_router
from signalalpha.quality.human_quality import evaluate_human_quality_batch
from signalalpha.opportunity.opportunity_potential import evaluate_opportunity_batch
from signalalpha.wiki.auth import (
    LOGIN_HTML, check_invite_code, is_public, make_token, verify_token,
    COOKIE_NAME, MAX_AGE_DAYS,
)
from signalalpha.wiki.autogen import WIKI_ROOT
from signalalpha.wiki.ranking import (
    VALID_DIRECTION, VALID_FILTERS, VALID_SCORE, VALID_SECTORS,
    fetch_rankings,
)
from signalalpha.wiki.brief import build_daily_brief
from signalalpha.wiki.cli import _to_dict
from signalalpha.classification.strategic_classification import (
    classify_candidate, build_strategic_view,
)
from signalalpha.portfolio.portfolio_context import build_portfolio_context
from signalalpha.wiki.research import build_research
from signalalpha.wiki.validate import validate

app = FastAPI(title="SignalAlpha")
app.include_router(admin_router)


class _AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if is_public(request.url.path):
            return await call_next(request)
        token = request.cookies.get(COOKIE_NAME, "")
        if not verify_token(token):
            if request.url.path.startswith(("/api/", "/top10", "/brief", "/admin")):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            return RedirectResponse("/login", status_code=302)
        return await call_next(request)


if os.getenv("AUTH_ENABLED", "0") == "1":
    app.add_middleware(_AuthMiddleware)


@app.get("/login", response_class=HTMLResponse)
async def login_page():
    return LOGIN_HTML.replace("{error}", "")


@app.post("/login")
async def login_submit(code: str = Form(...)):
    if not check_invite_code(code):
        err = '<div class="err">Invalid invite code. Please try again.</div>'
        return HTMLResponse(LOGIN_HTML.replace("{error}", err), status_code=401)
    resp = RedirectResponse("/", status_code=302)
    resp.set_cookie(
        COOKIE_NAME, make_token(),
        max_age=MAX_AGE_DAYS * 86400,
        httponly=True, samesite="lax",
    )
    return resp


@app.get("/logout")
async def logout():
    resp = RedirectResponse("/login", status_code=302)
    resp.delete_cookie(COOKIE_NAME)
    return resp


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
  /* ── Dark mode (default) ── */
  :root {
    --bg-page:     #1e1e1e;
    --bg-card:     #2a2a2a;
    --bg-card2:    #252525;
    --bg-card3:    #303030;
    --border:      #3d3d3d;
    --text:        #f0f0f0;
    --text-2:      #d4d4d4;
    --text-muted:  #9e9e9e;
    --text-muted2: #888888;
    --text-dim:    #757575;
    --text-faint:  #555555;
  }
  /* ── Light mode overrides ── */
  body.light {
    --bg-page:     #ffffff;
    --bg-card:     #ffffff;
    --bg-card2:    #f5f5f5;
    --bg-card3:    #ebebeb;
    --border:      #d4d4d4;
    --text:        #1a1a1a;
    --text-2:      #333333;
    --text-muted:  #555555;
    --text-muted2: #6b6b6b;
    --text-dim:    #757575;
    --text-faint:  #9e9e9e;
  }

  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: 'Segoe UI', system-ui, sans-serif;
    background: var(--bg-page); color: var(--text);
    min-height: 100vh; display: flex; flex-direction: column; align-items: center;
    padding: 1.5rem 1rem; transition: background .2s, color .2s;
  }
  header {
    width: 100%; max-width: 1200px;
    display: flex; align-items: center; gap: 1rem;
    margin-bottom: 1rem;
  }
  header h1 { font-size: 1.3rem; font-weight: 700; letter-spacing: -.02em; }
  header .tagline { color: var(--text-dim); font-size: .8rem; }

  /* Tabs */
  .tabs {
    width: 100%; max-width: 1200px;
    display: flex; border-bottom: 1px solid var(--border);
    margin-bottom: 1.5rem;
  }
  .tab-btn {
    background: none; border: none; color: var(--text-muted);
    padding: .55rem 1.2rem; font-size: .88rem; font-weight: 600;
    cursor: pointer; border-bottom: 2px solid transparent;
    margin-bottom: -1px; transition: color .12s, border-color .12s;
  }
  .tab-btn:hover { color: var(--text-muted2); }
  .tab-btn.active { color: #818cf8; border-bottom-color: #6366f1; }
  body.light .tab-btn.active { color: #4f46e5; border-bottom-color: #4f46e5; }

  .tab-panel { display: none; width: 100%; max-width: 1200px; }
  .tab-panel.active { display: block; }

  /* Card */
  .card {
    background: var(--bg-card); border: 1px solid var(--border);
    border-radius: 10px; padding: 1.1rem; margin-bottom: 1rem;
  }
  .card-title {
    font-size: .72rem; color: var(--text-muted);
    text-transform: uppercase; letter-spacing: .07em;
    margin-bottom: .85rem; display: flex; align-items: center; gap: .5rem;
  }
  .card-title .actions { margin-left: auto; display: flex; gap: .4rem; }

  /* ── Daily Brief ──────────────────────────────────────── */
  .brief-grid {
    display: flex; flex-direction: column; gap: .6rem;
  }
  .signal-card {
    background: var(--bg-card2); border: 1px solid var(--border); border-radius: 9px;
    padding: .85rem 1rem; display: grid;
    grid-template-columns: 200px 1fr auto;
    gap: .5rem 1.2rem; align-items: start;
    cursor: pointer; transition: border-color .15s, background .15s;
  }
  .signal-card:hover { border-color: #4f46e5; background: var(--bg-card3); }

  .sc-name { font-weight: 700; font-size: .9rem; color: var(--text); margin-bottom: .3rem; }
  .sc-meta { font-size: .73rem; color: var(--text-dim); }

  .sc-stats {
    display: flex; flex-wrap: wrap; gap: .4rem .9rem; align-items: center;
  }
  .stat-item { font-size: .78rem; }
  .stat-label { color: var(--text-muted); margin-right: .2rem; }
  .stat-val { font-weight: 600; }
  .pos { color: #3fb950; }
  .neg { color: #f85149; }
  .neu { color: var(--text-2); }
  .amber { color: #d29922; }
  body.light .pos   { color: #1a7f37; }
  body.light .neg   { color: #cf222e; }
  body.light .amber { color: #9a6700; }

  .sc-right { display: flex; flex-direction: column; align-items: flex-end; gap: .4rem; }

  .status-pill {
    display: inline-block; padding: .18rem .6rem;
    border-radius: 999px; font-size: .68rem; font-weight: 700; letter-spacing: .04em;
    white-space: nowrap;
  }
  .pill-validated  { background: #0d2818; color: #3fb950; border: 1px solid #238636; }
  .pill-borderline { background: #2d1f00; color: #d29922; border: 1px solid #9e6a03; }
  .pill-graveyard  { background: var(--bg-card3); color: var(--text-muted); border: 1px solid var(--border); }

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
    border-top: 1px solid var(--border); padding-top: .7rem;
  }
  .drilldown.open { display: block; }
  .drilldown-hdr {
    font-size: .72rem; color: var(--text-muted); text-transform: uppercase;
    letter-spacing: .06em; margin-bottom: .5rem;
    display: flex; align-items: center; gap: .5rem;
  }
  .ev-tbl { width: 100%; border-collapse: collapse; font-size: .75rem; }
  .ev-tbl th {
    text-align: left; color: var(--text-muted); font-size: .68rem;
    text-transform: uppercase; letter-spacing: .05em;
    padding: .3rem .5rem; border-bottom: 1px solid var(--border);
  }
  .ev-tbl td { padding: .28rem .5rem; border-bottom: 1px solid var(--bg-card2); color: var(--text-2); }
  .ev-tbl tr:hover td { background: var(--bg-card); }
  .ev-loading { color: var(--text-dim); font-size: .75rem; font-style: italic; padding: .5rem 0; }

  /* Divider */
  .brief-meta {
    font-size: .73rem; color: var(--text-dim); margin-bottom: .85rem;
    display: flex; align-items: center; gap: .5rem;
  }

  /* Empty / loading */
  .state-msg { color: var(--text-dim); font-size: .82rem; font-style: italic; padding: 1.5rem 0; text-align: center; }

  /* ── Wiki Editor ──────────────────────────────────────── */
  .editor-layout {
    display: grid; grid-template-columns: 220px 1fr;
    gap: 1rem; align-items: start;
  }
  @media(max-width:760px){ .editor-layout { grid-template-columns: 1fr; } }

  .page-group-label {
    font-size: .7rem; color: var(--text-dim); text-transform: uppercase;
    letter-spacing: .06em; margin: .6rem 0 .3rem; padding: 0 .3rem;
  }
  .page-item {
    padding: .35rem .5rem; border-radius: 6px; cursor: pointer;
    font-size: .8rem; color: var(--text-muted2); white-space: nowrap;
    overflow: hidden; text-overflow: ellipsis;
    transition: background .12s, color .12s;
  }
  .page-item:hover { background: var(--border); color: var(--text); }
  .page-item.active { background: #312e81; color: #a5b4fc; }
  .no-pages { color: var(--text-dim); font-size: .78rem; font-style: italic; }

  textarea {
    width: 100%; height: 400px;
    background: var(--bg-page); color: var(--text);
    border: 1px solid var(--border); border-radius: 8px;
    padding: .75rem; font-family: 'Fira Code', monospace; font-size: .78rem;
    resize: vertical; outline: none;
  }
  textarea:focus { border-color: #6366f1; }

  .toolbar { display: flex; gap: .6rem; align-items: center; margin-top: .75rem; flex-wrap: wrap; }
  .file-btn {
    cursor: pointer; background: var(--border); color: var(--text-muted2);
    padding: .38rem .8rem; border-radius: 7px; font-size: .8rem;
    border: 1px solid #3d4560; transition: background .12s;
  }
  .file-btn:hover { background: #3d4560; }
  input[type=file] { display: none; }
  #filename { font-size: .75rem; color: var(--text-dim); }

  button {
    background: #6366f1; color: #fff; border: none;
    padding: .42rem 1rem; border-radius: 7px; font-size: .84rem;
    font-weight: 600; cursor: pointer; transition: background .12s;
  }
  button:hover { background: #4f46e5; }
  button:disabled { background: var(--border); color: var(--text-dim); cursor: not-allowed; }
  button.secondary {
    background: var(--bg-card); border: 1px solid var(--border); color: var(--text-muted2); font-weight: 500;
  }
  button.secondary:hover { background: var(--border); }
  button.success { background: #166534; }
  button.success:hover { background: #14532d; }

  .spinner { display:none; width:15px; height:15px; border:2px solid var(--border);
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
  .stat-box { background:var(--bg-page); border:1px solid var(--border); border-radius:7px; padding:.35rem .7rem; font-size:.78rem; }
  .passes { display:flex; flex-direction:column; gap:.5rem; }
  .pass-row { border:1px solid var(--border); border-radius:7px; overflow:hidden; }
  .pass-hdr {
    display:flex; align-items:center; gap:.5rem;
    padding:.55rem .8rem; background:var(--bg-card3); cursor:pointer; user-select:none;
  }
  .pass-hdr:hover { background:var(--bg-card); }
  .pass-name { font-weight:600; font-size:.84rem; }
  .pass-counts { margin-left:auto; display:flex; gap:.35rem; }
  .pass-body { padding:.65rem .8rem; background:var(--bg-page); display:none; }
  .pass-body.open { display:block; }
  .issue-list { list-style:none; display:flex; flex-direction:column; gap:.4rem; }
  .issue { border-left:3px solid; padding:.4rem .6rem; border-radius:0 5px 5px 0; background:var(--bg-card2); font-size:.78rem; }
  .issue.fail { border-color:#f87171; }
  .issue.warn { border-color:#fbbf24; }
  .issue-rule { font-weight:700; font-family:monospace; font-size:.73rem; margin-bottom:.15rem; }
  .issue-msg { color:#cbd5e1; line-height:1.4; }
  .issue-loc { color:var(--text-dim); font-size:.7rem; margin-top:.15rem; }
  .empty { color:var(--text-dim); font-size:.78rem; font-style:italic; }

  /* ── How It Works ─────────────────────────────────── */
  .howto-wrap { max-width: 860px; }
  .howto-section { margin-bottom: 2rem; }
  .howto-h2 {
    font-size: .95rem; font-weight: 700; color: #a5b4fc;
    margin-bottom: .75rem; padding-bottom: .4rem;
    border-bottom: 1px solid var(--border);
  }
  .howto-p { font-size: .83rem; color: var(--text-2); line-height: 1.75; margin-bottom: .6rem; }

  .pipeline { display:flex; align-items:center; flex-wrap:wrap; gap:.3rem; margin:1rem 0; }
  .pipe-step {
    background:var(--bg-card); border:1px solid var(--border); border-radius:8px;
    padding:.55rem 1rem;
  }
  .pipe-step strong { display:block; font-size:.68rem; color:#a5b4fc; letter-spacing:.05em; text-transform:uppercase; margin-bottom:.15rem; }
  .pipe-step span { font-size:.76rem; color:var(--text-muted); }
  .pipe-arrow { color:#4f46e5; font-size:1.1rem; padding:0 .2rem; }

  .metric-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:.75rem; margin-top:.75rem; }
  @media(max-width:760px){ .metric-grid { grid-template-columns:1fr; } }
  .metric-card {
    background:var(--bg-card2); border:1px solid var(--border); border-radius:9px; padding:.9rem 1rem;
  }
  .metric-name { font-size:.8rem; font-weight:700; color:var(--text); margin-bottom:.25rem; }
  .metric-abbr { font-size:.68rem; color:#6366f1; font-family:monospace; margin-bottom:.4rem; }
  .metric-desc { font-size:.75rem; color:var(--text-muted); line-height:1.65; }
  .metric-good { display:inline-block; margin-top:.4rem; font-size:.68rem; color:#4ade80; }
  .metric-bad  { display:inline-block; margin-top:.4rem; font-size:.68rem; color:#f87171; }

  .signal-list { display:flex; flex-direction:column; gap:.6rem; }
  .signal-item { background:var(--bg-card2); border:1px solid var(--border); border-radius:8px; padding:.8rem 1rem; }
  .signal-item-name { font-weight:700; color:var(--text); font-size:.85rem; margin-bottom:.3rem; }
  .signal-item-desc { font-size:.75rem; color:var(--text-muted); line-height:1.65; }

  .dir-explainer { display:grid; grid-template-columns:1fr 1fr; gap:.75rem; margin-top:.75rem; }
  @media(max-width:760px){ .dir-explainer { grid-template-columns:1fr; } }
  .dir-card { border-radius:9px; padding:1rem; border:1px solid var(--border); background:var(--bg-card2); }
  .dir-card-long  { background:#0d2818; border-color:#238636; }
  .dir-card-mid   { background:#0d1f2d; border-color:#1d6fa6; }
  .dir-card-opp   { background:#2d1f00; border-color:#9e6a03; }
  .dir-card-title { font-weight:700; font-size:.88rem; margin-bottom:.5rem; color:var(--text); }
  .dir-card-long .dir-card-title { color:#3fb950; }
  .dir-card-mid  .dir-card-title { color:#58b6e8; }
  .dir-card-opp  .dir-card-title { color:#d29922; }
  .dir-card p { font-size:.76rem; color:var(--text-muted); line-height:1.65; }

  /* ── Top 10 ───────────────────────────────────────── */
  .filter-bar { display:flex; gap:1rem; align-items:center; flex-wrap:wrap; padding:.2rem 0; }
  .filter-group { display:flex; flex-direction:column; gap:.25rem; }
  .filter-label { font-size:.68rem; color:var(--text-muted); text-transform:uppercase; letter-spacing:.06em; }
  .filter-sel {
    background:var(--bg-page); color:var(--text); border:1px solid var(--border);
    border-radius:6px; padding:.32rem .65rem; font-size:.8rem; outline:none; cursor:pointer;
  }
  .filter-sel:focus { border-color:#6366f1; }

  .podium-grid { display:grid; grid-template-columns:1fr 1fr 1fr; gap:1rem; margin-bottom:1rem; }
  @media(max-width:760px) { .podium-grid { grid-template-columns:1fr; } }

  .podium-card {
    background:var(--bg-card); border:2px solid var(--border); border-radius:12px;
    padding:1.2rem 1.1rem; position:relative; display:flex; flex-direction:column; gap:.45rem;
    transition:transform .15s;
  }
  .podium-card:hover { transform:translateY(-2px); }
  .podium-card.rank-1 { border-color:#f59e0b; box-shadow:0 0 22px rgba(245,158,11,.13); }
  .podium-card.rank-2 { border-color:var(--text-muted2); }
  .podium-card.rank-3 { border-color:#b87333; }

  .podium-medal {
    position:absolute; top:.85rem; right:1rem;
    font-size:1.5rem; line-height:1; opacity:.6;
  }

  .podium-ticker { font-size:1.7rem; font-weight:900; letter-spacing:-.03em; }
  .rank-1 .podium-ticker { color:#f59e0b; }
  .rank-2 .podium-ticker { color:var(--text-2); }
  .rank-3 .podium-ticker { color:#cd9a60; }

  .podium-company { font-size:.77rem; color:var(--text-muted); margin-top:-.2rem; }

  .sector-badge {
    display:inline-block; padding:.12rem .45rem; border-radius:4px;
    font-size:.65rem; font-weight:700; letter-spacing:.04em; white-space:nowrap;
  }
  .sec-ai_infra      { background:#1a1f6e; color:#a5b4fc; border:1px solid #4f55c8; }
  .sec-space_defense { background:#0d3b2a; color:#3fb950; border:1px solid #238636; }
  .sec-telecom       { background:#2d1e00; color:#d29922; border:1px solid #9e6a03; }
  .sec-unknown       { background:var(--bg-card3); color:var(--text-dim); border:1px solid var(--border); }

  .podium-stats { display:flex; flex-wrap:wrap; gap:.35rem .75rem; margin-top:.15rem; }

  .score-bar-wrap { height:4px; background:var(--border); border-radius:999px; margin-top:.5rem; overflow:hidden; }
  .score-bar-fill { height:100%; border-radius:999px; transition:width .5s; }
  .rank-1 .score-bar-fill { background:#f59e0b; }
  .rank-2 .score-bar-fill { background:var(--text-muted2); }
  .rank-3 .score-bar-fill { background:#b87333; }
  .rank-other .score-bar-fill { background:#6366f1; }

  .lb-tbl { width:100%; border-collapse:collapse; font-size:.8rem; }
  .lb-tbl th {
    text-align:left; color:var(--text-muted); font-size:.68rem; text-transform:uppercase;
    letter-spacing:.05em; padding:.4rem .7rem; border-bottom:1px solid var(--border);
  }
  .lb-tbl td { padding:.42rem .7rem; border-bottom:1px solid var(--bg-card2); color:var(--text-2); }
  .lb-tbl tbody tr { cursor:pointer; transition:background .1s; }
  .lb-tbl tbody tr:hover td { background:var(--bg-card); }
  .lb-rank { font-weight:700; color:var(--text-dim); }
  .lb-ticker-cell { font-weight:700; color:var(--text); font-size:.88rem; }
  .lb-bar-cell { width:110px; }
  .lb-bar { height:5px; background:var(--border); border-radius:999px; margin-top:.3rem; overflow:hidden; }
  .lb-bar-fill { height:100%; background:#6366f1; border-radius:999px; }
  .lb-bar-fill.short { background:#f97316; }

  .dir-toggle { display:flex; border:1px solid var(--border); border-radius:7px; overflow:hidden; }
  .dir-btn { background:none; border:none; color:var(--text-muted); padding:.35rem .9rem; font-size:.82rem; font-weight:600; cursor:pointer; transition:background .12s,color .12s; }
  .dir-btn.active-long  { background:#14532d; color:#4ade80; }
  .dir-btn.active-opp { background:#431407; color:#fb923c; }

  .podium-card.opp-rank-1 { border-color:#f97316; box-shadow:0 0 22px rgba(249,115,22,.15); }
  .podium-card.opp-rank-2 { border-color:#fb923c; }
  .podium-card.opp-rank-3 { border-color:#fdba74; }
  .opp-rank-1 .podium-ticker { color:#f97316; }
  .opp-rank-2 .podium-ticker { color:#fb923c; }
  .opp-rank-3 .podium-ticker { color:#fdba74; }
  .opp-rank-1 .score-bar-fill { background:#f97316; }
  .opp-rank-2 .score-bar-fill { background:#fb923c; }
  .opp-rank-3 .score-bar-fill { background:#fdba74; }

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

  .all-modes-badge {
    display:inline-block; padding:.1rem .38rem; border-radius:4px;
    font-size:.6rem; font-weight:700; letter-spacing:.04em; white-space:nowrap;
    background:#1f1a36; color:#a78bfa; border:1px solid #4c3d8f;
    vertical-align:middle;
  }
  body.light .all-modes-badge { background:#f3f0ff; color:#6d28d9; border-color:#c4b5fd; }

  .risk-badge {
    display:inline-block; padding:.11rem .42rem; border-radius:4px;
    font-size:.62rem; font-weight:700; letter-spacing:.05em; white-space:nowrap;
  }
  .risk-low  { background:#0d2818; color:#3fb950; border:1px solid #238636; }
  .risk-med  { background:#2d1f00; color:#d29922; border:1px solid #9e6a03; }
  .risk-high { background:#2d0f0f; color:#f85149; border:1px solid #8b2020; }

  /* ── Human Quality badges ──────────────────────────────────────────────── */
  .hq-row {
    display:flex; gap:.3rem; flex-wrap:wrap; align-items:center;
    margin-top:.4rem;
  }
  .hq-badge {
    display:inline-block; padding:.1rem .35rem; border-radius:3px;
    font-size:.58rem; font-weight:700; letter-spacing:.04em; white-space:nowrap;
  }
  .hq-pass    { background:#0d2818; color:#3fb950; border:1px solid #238636; }
  .hq-warn    { background:#2d1f00; color:#d29922; border:1px solid #9e6a03; }
  .hq-fail    { background:#2d0f0f; color:#f85149; border:1px solid #8b2020; }
  .hq-unknown { background:var(--bg-card3); color:var(--text-muted); border:1px solid var(--border); }
  .hq-score   { font-size:.65rem; color:var(--text-dim); margin-left:.15rem; }
  body.light .hq-pass    { background:#dafbe1; color:#1a7f37; border-color:#82cfaf; }
  body.light .hq-warn    { background:#fff8c5; color:#9a6700; border-color:#d4a72c; }
  body.light .hq-fail    { background:#ffebe9; color:#cf222e; border-color:#ff8182; }
  body.light .hq-unknown { background:var(--bg-card2); color:var(--text-muted); border-color:var(--border); }

  /* TA overlay */
  .ta-overlay {
    display:flex; gap:.5rem; flex-wrap:wrap; align-items:center;
    margin-top:.55rem; padding:.4rem .55rem;
    background:var(--bg-card2); border:1px solid var(--border); border-radius:6px;
    font-size:.72rem;
  }
  .ta-pill {
    display:inline-block; padding:.1rem .45rem; border-radius:4px;
    font-size:.65rem; font-weight:700; letter-spacing:.04em;
  }
  .ta-pill.pos { background:#0d2818; color:#3fb950; border:1px solid #238636; }
  .ta-pill.neg { background:#2d0f0f; color:#f85149; border:1px solid #8b2020; }
  .ta-pill.neu { background:var(--bg-card3); color:var(--text-muted); border:1px solid var(--border); }
  .ta-item { color:var(--text-2); font-size:.72rem; }
  .ta-item b { font-weight:700; }

  /* Toast */
  #toast {
    position:fixed; bottom:1.5rem; right:1.5rem;
    background:var(--bg-card); border:1px solid var(--border); border-radius:8px;
    padding:.6rem 1rem; font-size:.8rem; color:var(--text);
    opacity:0; transition:opacity .2s; pointer-events:none;
  }
  #toast.show { opacity:1; }

  /* Disclaimer footer */
  .disclaimer-bar {
    width:100%; max-width:1200px; margin-top:2rem; padding:.55rem .8rem;
    background:var(--bg-card2); border:1px solid var(--border); border-radius:7px;
    font-size:.75rem; font-weight:600; color:var(--text-muted); text-align:center; line-height:1.5;
  }

  /* Stock detail modal */
  .modal-backdrop {
    display:none; position:fixed; inset:0; background:rgba(0,0,0,.7);
    z-index:1000; align-items:center; justify-content:center;
    padding:1rem;
  }
  .modal-backdrop.open { display:flex; }
  .modal-box {
    background:var(--bg-card); border:1px solid var(--border); border-radius:12px;
    width:100%; max-width:820px; max-height:88vh; overflow-y:auto;
    padding:1.4rem 1.6rem; position:relative;
  }
  .modal-close {
    position:absolute; top:.8rem; right:1rem;
    background:none; border:none; color:var(--text-faint); font-size:1.2rem;
    cursor:pointer; line-height:1;
  }
  .modal-close:hover { color:var(--text); }
  .modal-ticker { font-size:1.6rem; font-weight:900; letter-spacing:-.03em; }
  .modal-name { font-size:.8rem; color:var(--text-muted); margin-bottom:1rem; }
  .modal-section { margin-top:1.1rem; }
  .modal-section-title {
    font-size:.68rem; text-transform:uppercase; letter-spacing:.08em;
    color:var(--text-muted2); margin-bottom:.5rem; border-bottom:1px solid var(--border);
    padding-bottom:.3rem;
  }
  .rank-chip {
    display:inline-block; padding:.1rem .45rem; border-radius:4px;
    font-size:.68rem; font-weight:700; background:#14532d; color:#4ade80;
    border:1px solid #166534; margin:.15rem;
  }
  .rank-chip.opp { background:#431407; color:#fb923c; border-color:#7c2d12; }
  .rank-chip.mid { background:#164e63; color:#22d3ee; border-color:#0e7490; }

  /* ── Research button ──────────────────────────────────────────────────── */
  .research-btn {
    display:inline-block; margin-top:.4rem; padding:.28rem .65rem;
    font-size:.72rem; font-weight:600; border-radius:5px; cursor:pointer;
    background:rgba(99,102,241,.13); color:#a5b4fc;
    border:1px solid rgba(99,102,241,.3);
    transition:background .12s, color .12s;
  }
  .research-btn:hover { background:rgba(99,102,241,.25); color:#c7d2fe; }

  /* ── Opportunity badge ────────────────────────────────────────────────── */
  .opp-badge { display:inline-block; padding:.15rem .5rem; border-radius:4px; font-size:.65rem; font-weight:700; letter-spacing:.03em; }
  .opp-high    { background:#16a34a; color:#fff; }
  .opp-medium  { background:#d97706; color:#fff; }
  .opp-low     { background:#dc2626; color:#fff; }
  .opp-unknown { background:#6b7280; color:#fff; }

  /* ── Research modal sections ──────────────────────────────────────────── */
  .rs-signal-stat { display:flex; gap:.5rem; flex-wrap:wrap; margin:.5rem 0; }
  .rs-stat-pill {
    background:var(--bg-card3); border:1px solid var(--border);
    border-radius:6px; padding:.3rem .7rem; font-size:.72rem;
  }
  .rs-stat-pill b { display:block; font-size:1rem; font-weight:800; }
  .rs-stat-pill span { color:var(--text-muted); font-size:.65rem; }
  .rs-badge {
    display:inline-block; padding:.15rem .5rem; border-radius:4px;
    font-size:.68rem; font-weight:700; margin:.15rem .1rem;
  }
  .rs-pass    { background:#16a34a; color:#fff; }
  .rs-warn    { background:#d97706; color:#fff; }
  .rs-fail    { background:#dc2626; color:#fff; }
  .rs-unknown { background:#6b7280; color:#fff; }
  .rs-fresh   { background:#16a34a; color:#fff; }
  .rs-stale   { background:#d97706; color:#fff; }
  .rs-missing { background:#6b7280; color:#fff; }
  .rs-steps { padding-left:1.2rem; margin:.4rem 0; }
  .rs-steps li { font-size:.8rem; color:var(--text-muted); margin:.3rem 0; line-height:1.4; }
  .rs-history-row { font-size:.78rem; color:var(--text-muted); margin:.2rem 0; }

  /* ── Why This Candidate Is Here ────────────────────────────────────────── */
  .why-grid { display:flex; flex-direction:column; gap:.55rem; margin:.2rem 0; }
  .why-row  { display:flex; align-items:flex-start; gap:.65rem; }
  .why-label {
    flex-shrink:0; font-size:.6rem; font-weight:800; letter-spacing:.07em;
    padding:.17rem .5rem; border-radius:.25rem;
    min-width:5.8rem; text-align:center; margin-top:.12rem;
  }
  .why-text { font-size:.8rem; color:var(--text-2); line-height:1.5; }
  .why-sig-validated  { background:#166534; color:#fff; }
  .why-sig-borderline { background:#92400e; color:#fff; }
  .why-sig-exploratory, .why-sig-none { background:#374151; color:#fff; }
  .why-label-quality  { background:#1e3a5f; color:#fff; }
  .why-label-opp      { background:#312e81; color:#fff; }
  .why-label-caution  { background:#7c2d12; color:#fff; }
  .why-caution-row .why-text { color:#fcd34d; }
  body.light .why-sig-validated  { background:#16a34a; color:#fff; }
  body.light .why-sig-borderline { background:#d97706; color:#fff; }
  body.light .why-sig-exploratory, body.light .why-sig-none { background:#6b7280; color:#fff; }
  body.light .why-label-quality  { background:#2563eb; color:#fff; }
  body.light .why-label-opp      { background:#7c3aed; color:#fff; }
  body.light .why-label-caution  { background:#ea580c; color:#fff; }
  body.light .why-caution-row .why-text { color:#c2410c; }
  .rs-dir-chip {
    display:inline-block; padding:.05rem .35rem; border-radius:3px;
    font-size:.65rem; font-weight:700; margin-right:.3rem;
  }
  .rs-dir-long { background:#166534; color:#fff; }
  .rs-dir-midterm { background:#155e75; color:#fff; }
  .rs-dir-opportunity { background:#7c2d12; color:#fff; }
  .rs-signal-status-validated { color:#4ade80; font-weight:700; }
  .rs-signal-status-borderline { color:#fbbf24; font-weight:700; }
  .rs-signal-status-exploratory { color:var(--text-faint); font-weight:700; }

  /* ── Portfolio Context ────────────────────────────────────────────────── */
  .pc-grid { display:flex; flex-wrap:wrap; gap:.45rem; margin:.35rem 0 .6rem; }
  .pc-badge {
    display:inline-block; padding:.18rem .55rem; border-radius:5px;
    font-size:.68rem; font-weight:700; letter-spacing:.04em;
  }
  .pc-role-Core        { background:#166534; color:#fff; }
  .pc-role-Growth      { background:#155e75; color:#fff; }
  .pc-role-Speculative { background:#7c2d12; color:#fff; }
  .pc-role-Watchlist   { background:#374151; color:#fff; }
  .pc-risk-Low    { background:#14532d; color:#fff; }
  .pc-risk-Medium { background:#713f12; color:#fff; }
  .pc-risk-High   { background:#7f1d1d; color:#fff; }
  .pc-conv-High   { background:#1e3a5f; color:#fff; }
  .pc-conv-Medium { background:#312e81; color:#fff; }
  .pc-conv-Low    { background:#374151; color:#fff; }
  .pc-theme { background:var(--bg-card3); color:var(--text-muted2); border:1px solid var(--border); }
  .pc-exposure { background:var(--bg-card3); color:var(--text-muted); border:1px solid var(--border); font-size:.63rem; }
  .pc-label {
    font-size:.6rem; font-weight:700; letter-spacing:.06em;
    color:var(--text-muted); margin-right:.3rem;
  }
  .pc-summary {
    font-size:.78rem; color:var(--text-muted); line-height:1.5; margin-top:.5rem;
  }
  .pc-conv-reason {
    font-size:.73rem; color:var(--text-2); margin-top:.2rem;
  }
  body.light .pc-role-Core        { background:#16a34a; }
  body.light .pc-role-Growth      { background:#0891b2; }
  body.light .pc-role-Speculative { background:#ea580c; }
  body.light .pc-role-Watchlist   { background:#6b7280; }
  body.light .pc-risk-Low    { background:#16a34a; }
  body.light .pc-risk-Medium { background:#d97706; }
  body.light .pc-risk-High   { background:#dc2626; }
  body.light .pc-conv-High   { background:#2563eb; }
  body.light .pc-conv-Medium { background:#7c3aed; }
  body.light .pc-conv-Low    { background:#6b7280; }

  /* ── Portfolio Context tab ────────────────────────────────────────────── */
  .ptab-stats {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: .75rem; margin-bottom: .75rem;
  }
  .ptab-stat-card {
    background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px;
    padding: .85rem 1rem;
  }
  .ptab-stat-title {
    font-size: .65rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase;
    color: var(--text-muted); margin-bottom: .55rem;
  }
  .ptab-dist { display: flex; flex-wrap: wrap; gap: .3rem; }
  .ptab-theme-grid {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    gap: .6rem; margin-top: .6rem;
  }
  .ptab-theme-card {
    background: var(--bg-card2); border: 1px solid var(--border); border-radius: 8px;
    padding: .65rem .8rem;
  }
  .ptab-theme-name {
    font-size: .72rem; font-weight: 700; color: var(--text-2); margin-bottom: .4rem;
  }
  .ptab-theme-tickers { display: flex; flex-wrap: wrap; gap: .25rem; }
  .ptab-ticker-chip {
    font-size: .65rem; font-weight: 700; padding: .12rem .4rem; border-radius: 4px;
    background: var(--bg-card3); color: var(--text-muted2); border: 1px solid var(--border);
    cursor: pointer;
  }
  .ptab-ticker-chip:hover { color: #a5b4fc; border-color: #6366f1; }
  .ptab-tbl { width: 100%; border-collapse: collapse; font-size: .77rem; margin-top: .5rem; }
  .ptab-tbl th {
    text-align: left; color: var(--text-muted); font-size: .66rem; text-transform: uppercase;
    letter-spacing: .05em; padding: .3rem .6rem; border-bottom: 1px solid var(--border);
  }
  .ptab-tbl td { padding: .35rem .6rem; border-bottom: 1px solid var(--bg-card2); vertical-align: middle; }
  .ptab-tbl tr:hover td { background: var(--bg-card3); }
  .ptab-ticker-link { font-weight: 700; color: var(--text); background: none; border: none;
    cursor: pointer; padding: 0; font-size: .77rem; }
  .ptab-ticker-link:hover { color: #a5b4fc; }

  /* ── Strategic View tab ──────────────────────────────────────────────── */
  .strat-grid {
    display: grid; grid-template-columns: repeat(3, 1fr); gap: .75rem; margin-bottom: .75rem;
  }
  @media (max-width: 900px) { .strat-grid { grid-template-columns: 1fr; } }
  .strat-col {
    background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px;
    padding: .85rem 1rem; display: flex; flex-direction: column; gap: .55rem;
  }
  .strat-col-hdr { margin-bottom: .2rem; }
  .strat-col-title {
    font-size: .78rem; font-weight: 800; letter-spacing: .05em; text-transform: uppercase;
  }
  .strat-col-title.asymmetric   { color: #f59e0b; }
  .strat-col-title.transitional { color: #60a5fa; }
  .strat-col-title.compounder   { color: #4ade80; }
  .strat-col-title.signal_play  { color: #a78bfa; }
  .strat-col-subtitle { font-size: .69rem; color: var(--text-muted); margin-top: .15rem; }
  .strat-card {
    background: var(--bg-card2); border: 1px solid var(--border); border-radius: 8px;
    padding: .6rem .75rem; display: flex; flex-direction: column; gap: .3rem;
  }
  .strat-card-hdr { display: flex; align-items: center; gap: .4rem; flex-wrap: wrap; }
  .strat-ticker-btn {
    font-weight: 800; font-size: .88rem; color: var(--text); background: none;
    border: none; cursor: pointer; padding: 0;
  }
  .strat-ticker-btn:hover { color: #a5b4fc; }
  .strat-name   { font-size: .68rem; color: var(--text-muted); }
  .strat-reason { font-size: .71rem; color: var(--text-muted2); line-height: 1.5; }
  .strat-themes { display: flex; flex-wrap: wrap; gap: .25rem; margin-top: .1rem; }
  .strat-signal-row {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: .5rem;
  }
  body.light .strat-col-title.asymmetric   { color: #d97706; }
  body.light .strat-col-title.transitional { color: #2563eb; }
  body.light .strat-col-title.compounder   { color: #16a34a; }
  body.light .strat-col-title.signal_play  { color: #7c3aed; }
  body.light .strat-card { background: var(--bg-card3); }

  /* ── Light mode overrides ─────────────────────────────────────────────── */
  body.light .signal-card { background:var(--bg-card2); }
  body.light .signal-card:hover { background:var(--bg-card3); border-color:#6366f1; }
  body.light .metric-card { background:var(--bg-card2); }
  body.light .signal-item { background:var(--bg-card2); }
  body.light .pipe-step { background:var(--bg-card2); }
  body.light .pass-hdr:hover { background:var(--bg-card3); }
  body.light .pass-body { background:var(--bg-page); }
  body.light .ev-tbl tr:hover td { background:var(--bg-card2); }
  body.light .lb-tbl tbody tr:hover td { background:var(--bg-card2); }
  body.light .stat-box { background:var(--bg-page); }
  body.light .dir-card-long { background:#f0fff4; border-color:#82cfaf; }
  body.light .dir-card-long .dir-card-title { color:#1a7f37; }
  body.light .dir-card-mid  { background:#f0f8ff; border-color:#54aeff; }
  body.light .dir-card-mid  .dir-card-title { color:#0969da; }
  body.light .dir-card-opp  { background:#fffbeb; border-color:#d4a72c; }
  body.light .dir-card-opp  .dir-card-title { color:#9a6700; }
  body.light .dir-card p { color:var(--text-muted); }
  body.light .howto-h2 { color:#4f46e5; }
  body.light .filter-sel { background:var(--bg-card); color:var(--text); border-color:var(--border); }
  body.light textarea { background:var(--bg-card); color:var(--text); border-color:var(--border); }
  body.light .file-btn { background:var(--bg-card2); color:var(--text-muted); border-color:var(--border); }
  body.light .file-btn:hover { background:var(--bg-card3); }
  body.light button.secondary { background:var(--bg-card); border-color:var(--border); color:var(--text-muted); }
  body.light button.secondary:hover { background:var(--bg-card2); }
  body.light .page-item:hover { background:var(--bg-card3); color:var(--text); }
  body.light .pill-validated  { background:#dafbe1; color:#1a7f37; border-color:#82cfaf; }
  body.light .pill-borderline { background:#fff8c5; color:#9a6700; border-color:#d4a72c; }
  body.light .pill-graveyard  { background:var(--bg-card2); color:var(--text-muted); border-color:var(--border); }
  body.light .ctx-current { background:#dafbe1; color:#1a7f37; border-color:#82cfaf; }
  body.light .ctx-stale   { background:#fff8c5; color:#9a6700; border-color:#d4a72c; }
  body.light .ctx-missing { background:var(--bg-card2); color:var(--text-muted); border-color:var(--border); }
  body.light .risk-low  { background:#dafbe1; color:#1a7f37; border-color:#82cfaf; }
  body.light .risk-med  { background:#fff8c5; color:#9a6700; border-color:#d4a72c; }
  body.light .risk-high { background:#ffebe9; color:#cf222e; border-color:#ff8182; }
  body.light .ta-pill.pos { background:#dafbe1; color:#1a7f37; border-color:#82cfaf; }
  body.light .ta-pill.neg { background:#ffebe9; color:#cf222e; border-color:#ff8182; }
  body.light .ta-pill.neu { background:var(--bg-card2); color:var(--text-muted); border-color:var(--border); }
  body.light .ta-overlay { background:var(--bg-card2); border-color:var(--border); }
  body.light .ta-item { color:var(--text-muted); }
  body.light .sec-ai_infra      { background:#ddf4ff; color:#0969da; border-color:#54aeff; }
  body.light .sec-space_defense { background:#dafbe1; color:#1a7f37; border-color:#82cfaf; }
  body.light .sec-telecom       { background:#fff8c5; color:#9a6700; border-color:#d4a72c; }
  body.light .rank-2 .podium-ticker { color:var(--text-2); }
  body.light #toast { background:var(--bg-card); border-color:var(--border); color:var(--text); }
  body.light .disclaimer-bar { background:#fff8c5; border-color:#d4a72c; color:#6e4f00; }
  body.light .rank-chip     { background:#dafbe1; color:#1a7f37; border-color:#82cfaf; }
  body.light .rank-chip.opp { background:#fff8c5; color:#9a6700; border-color:#d4a72c; }
  body.light .rank-chip.mid { background:#ddf4ff; color:#0969da; border-color:#54aeff; }

  /* Mobile layout */
  @media(max-width:640px) {
    body { padding:1rem .5rem; }
    .tabs { gap:0; overflow-x:auto; }
    .tab-btn { padding:.45rem .7rem; font-size:.78rem; white-space:nowrap; }
    .filter-bar { gap:.5rem; }
    .dir-btns { flex-wrap:wrap; gap:.25rem; }
    .podium-grid { grid-template-columns:1fr !important; }
    .lb-tbl-wrap { overflow-x:auto; -webkit-overflow-scrolling:touch; }
    .lb-tbl { font-size:.72rem; min-width:560px; }
    .lb-tbl th, .lb-tbl td { padding:.35rem .45rem; }
    .modal-box { padding:1rem; border-radius:8px; }
    .modal-ticker { font-size:1.3rem; }
  }
</style>
</head>
<body>

<header>
  <h1>SignalAlpha</h1>
  <span class="tagline">Signal-driven research system</span>
  <div style="margin-left:auto;display:flex;gap:.5rem;align-items:center">
    <button id="theme-btn" onclick="toggleTheme()"
      style="background:none;border:1px solid var(--border);color:var(--text-muted);
             padding:.3rem .75rem;border-radius:6px;font-size:.78rem;font-weight:600;cursor:pointer;
             transition:background .15s,color .15s">☀ Light</button>
    <a href="/logout"
      style="background:none;border:1px solid var(--border);color:var(--text-muted);
             padding:.3rem .75rem;border-radius:6px;font-size:.78rem;font-weight:600;cursor:pointer;
             text-decoration:none;transition:background .15s,color .15s">Sign out</a>
  </div>
</header>

<div class="tabs">
  <button class="tab-btn active" onclick="switchTab('top10', this)">Top Research Candidates</button>
  <button class="tab-btn" onclick="switchTab('portfolio', this)">Portfolio Context</button>
  <button class="tab-btn" onclick="switchTab('strategic', this)">Strategic View</button>
  <button class="tab-btn" onclick="switchTab('editor', this)">Wiki Editor</button>
  <button class="tab-btn" onclick="switchTab('howto', this)">How It Works</button>
  <button class="tab-btn" onclick="switchTab('rotation', this)">Rotation Log</button>
  <button class="tab-btn" onclick="switchTab('brief', this)">Daily Brief</button>
</div>

<!-- ═══════════════════════ DAILY BRIEF TAB -->
<div class="tab-panel" id="tab-brief">
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
<div class="tab-panel active" id="tab-top10">
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
          <option value="blended">Blended (Signal &times; Quality &times; Opportunity)</option>
          <option value="investor">Investor Rank (Quality &amp; Opportunity weighted)</option>
        </select>
      </div>
      <div class="filter-group">
        <label class="filter-label">Direction</label>
        <div class="dir-toggle">
          <button id="dir-long"    class="dir-btn active-long"  onclick="setDirection('long')">Long</button>
          <button id="dir-midterm" class="dir-btn"              onclick="setDirection('midterm')">📈 Mid-term</button>
          <button id="dir-opp"     class="dir-btn"              onclick="setDirection('opportunity')">Opportunity</button>
        </div>
      </div>
      <div class="filter-group">
        <label class="filter-label">Active within</label>
        <select id="t10-recency" class="filter-sel" onchange="loadTop10()">
          <option value="90">Last 90 days</option>
          <option value="180">Last 180 days</option>
          <option value="365">Last 1 year</option>
          <option value="0">All time (no filter)</option>
        </select>
      </div>
      <div class="filter-group" style="justify-content:flex-end;gap:.4rem;flex-direction:row;align-items:flex-end">
        <button id="ta-toggle" class="secondary" style="font-size:.7rem;padding:.3rem .6rem" onclick="toggleTA()" title="Overlay RSI + moving average signals on each card">📊 Technical Analysis</button>
        <button class="secondary" style="font-size:.7rem;padding:.3rem .6rem" onclick="loadTop10()">↻ Refresh</button>
      </div>
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

<!-- ═══════════════════════ ROTATION LOG TAB -->
<div class="tab-panel" id="tab-rotation">
  <div class="card" style="padding:.7rem 1.1rem;margin-bottom:.75rem">
    <div class="filter-bar">
      <div class="filter-group">
        <label class="filter-label">Direction</label>
        <select id="rot-direction" class="filter-sel" onchange="loadRotation()">
          <option value="long">Long</option>
          <option value="midterm">Mid-term</option>
          <option value="opportunity">Opportunity</option>
        </select>
      </div>
      <button class="secondary" style="font-size:.7rem;padding:.3rem .6rem;align-self:flex-end" onclick="loadRotation()">↻ Refresh</button>
    </div>
  </div>
  <div class="card" id="rot-card">
    <div class="card-title">Rotation History</div>
    <p class="state-msg">Select the tab to load.</p>
  </div>
</div>

<!-- ═══════════════════════ PORTFOLIO CONTEXT TAB -->
<div class="tab-panel" id="tab-portfolio">
  <div id="ptab-content">
    <p class="state-msg">Select the tab to load.</p>
  </div>
</div>

<!-- ═══════════════════════ STRATEGIC VIEW TAB -->
<div class="tab-panel" id="tab-strategic">
  <div id="strat-content">
    <p class="state-msg">Select the tab to load.</p>
  </div>
</div>

<!-- ═══════════════════════ HOW IT WORKS TAB -->
<div class="tab-panel" id="tab-howto">
<div class="card howto-wrap">

  <div class="howto-section">
    <div class="howto-h2">What is SignalAlpha?</div>
    <p class="howto-p">SignalAlpha is a <b>strategic research operating system</b>. It watches 68 stocks across AI, Space &amp; Defense, and Telecom for repeating statistical patterns — unusual volume spikes, patent grant clusters — and measures what historically followed. Patterns that prove statistically significant surface as research candidates and are then layered with quality, opportunity, portfolio context, and strategic classification.</p>
    <p class="howto-p">The system answers: <em>what deserves investigation right now, why it matters, what kind of opportunity it is, and how it fits a broader thesis.</em> It does not predict prices, recommend positions, or tell you what to do. Every candidate requires your own judgment before acting.</p>
  </div>

  <div class="howto-section">
    <div class="howto-h2">How Candidates Are Discovered — Step by Step</div>
    <div class="pipeline">
      <div class="pipe-step"><strong>1 — Detect</strong><span>Scan for unusual events: volume 2× the 60-day average, or 5+ patent grants in 30 days for a telecom company</span></div>
      <span class="pipe-arrow">→</span>
      <div class="pipe-step"><strong>2 — Backtest</strong><span>For every past occurrence, measure the stock's return vs its sector ETF over the next 10–45 days. Entry at next-day open, 10 bps slippage deducted</span></div>
      <span class="pipe-arrow">→</span>
      <div class="pipe-step"><strong>3 — Validate</strong><span>Paired t-test: p &lt; 0.05 required. Only patterns that pass this threshold are called <b>validated</b></span></div>
      <span class="pipe-arrow">→</span>
      <div class="pipe-step"><strong>4 — Holdout</strong><span>One final test on 2025+ data the system never trained on. Results are locked — no re-tuning after this</span></div>
    </div>
    <p class="howto-p" style="margin-top:1rem">Every 3 days, fresh prices and fundamentals are pulled and all signals re-run. The ranking only shows stocks where the signal fired in the <b>last 90 days</b> — so every candidate is active now, not a historical relic.</p>
  </div>

  <div class="howto-section">
    <div class="howto-h2">Five Layers of Context</div>
    <p class="howto-p">Every candidate passes through five compounding layers. Each layer adds a different type of reasoning — none replaces the one before it.</p>
    <div class="metric-grid">

      <div class="metric-card">
        <div class="metric-name">Layer 1 — Signal Score</div>
        <div class="metric-abbr">alpha × hit rate × log(N)</div>
        <div class="metric-desc">Pure backtest edge. A stock scores higher if it has big alpha <em>and</em> consistent wins <em>and</em> many historical events. A pattern with +10% alpha but only 3 past occurrences scores low — not enough history to trust. This is the base layer. Everything else adjusts it.</div>
        <span class="metric-good">Primary driver of ranking order</span>
      </div>

      <div class="metric-card">
        <div class="metric-name">Layer 2 — Human Quality</div>
        <div class="metric-abbr">4 checks: liquidity · trend · market · EPS</div>
        <div class="metric-desc">Four fundamentals checks applied as a soft multiplier on the signal score. <b>Liquidity:</b> sufficient daily volume. <b>Trend:</b> price above 50d and 200d MA. <b>Market alignment:</b> SPY above its 200d MA. <b>EPS growth:</b> earnings trajectory from fundamentals. A stock that fails multiple checks gets a slightly lower ranking — the signal still dominates, but quality adds confidence context.</div>
        <span class="metric-good">Multiplier range: 0.875–1.0 (narrow — signal stays primary)</span>
      </div>

      <div class="metric-card">
        <div class="metric-name">Layer 3 — Opportunity Potential</div>
        <div class="metric-abbr">6 checks: valuation · growth · extension · cap · sector · risk</div>
        <div class="metric-desc">Six checks that assess research upside — does this candidate still look interesting from a forward-looking perspective, or has the move already happened? <b>Valuation room:</b> P/E or P/B vs sector norms. <b>Growth support:</b> EPS + revenue growth. <b>Technical extension:</b> how far above SMA50/200 and 12-month return. <b>Market cap:</b> smaller caps have more room. <b>Sector tailwind:</b> sector-level momentum. <b>Risk penalty:</b> quality flags. Always shown as a badge — used as a ranking multiplier only in Blended and Investor modes.</div>
        <span class="metric-good">Status: high / medium / low / unknown</span>
      </div>

      <div class="metric-card">
        <div class="metric-name">Layer 4 — Portfolio Context</div>
        <div class="metric-abbr">role · risk bucket · conviction · themes · exposure</div>
        <div class="metric-desc">Soft heuristics that frame how a candidate fits into a broader portfolio thesis. <b>Role:</b> Core / Growth / Speculative / Watchlist — derived from signal × quality × opportunity. <b>Risk bucket:</b> Low / Medium / High. <b>Conviction:</b> High / Medium / Low with a one-line reason. <b>Themes and exposure profile:</b> what macro or sector narratives this candidate belongs to. Visible in the research modal and in the <b>Portfolio Context</b> tab.</div>
        <span class="metric-good">Visible in Portfolio Context tab and research modal</span>
      </div>

      <div class="metric-card">
        <div class="metric-name">Layer 5 — Strategic Classification</div>
        <div class="metric-abbr">Asymmetric · Transitional · Compounder · Signal Play</div>
        <div class="metric-desc">Classifies what <em>type</em> of research opportunity each candidate represents. <b>Asymmetric:</b> small/mid-cap with high uncertainty and high optionality — early-stage or pre-profitability. <b>Transitional:</b> companies changing regime — turnarounds, business model shifts, or sector reratings. <b>Compounder:</b> large-cap with durable recurring economics and consistent capital return. <b>Signal Play:</b> validated signal that does not fit neatly into the other three categories yet. This is the strategic brain of the platform — visible in the <b>Strategic View</b> tab.</div>
        <span class="metric-good">Visible in Strategic View tab</span>
      </div>

    </div>
  </div>

  <div class="howto-section">
    <div class="howto-h2">Research Candidates vs Investor Candidates</div>
    <p class="howto-p">The same candidate pool can be viewed through two different lenses, selectable in the <b>Rank by</b> dropdown.</p>
    <div class="dir-explainer">
      <div class="dir-card dir-card-long">
        <div class="dir-card-title">Research Candidates (default)</div>
        <p><b>Signal-first.</b> The backtest edge determines the ranking. Quality and opportunity add small adjustments. Use this to answer: <em>what has statistical evidence right now?</em> This is the discovery layer — it surfaces what deserves investigation regardless of fundamentals.</p>
      </div>
      <div class="dir-card dir-card-mid">
        <div class="dir-card-title">Investor Candidates</div>
        <p><b>Quality + opportunity weighted.</b> Same candidate pool, but quality and opportunity have a much wider impact on the final order (multiplier range 0.4–1.0 vs 0.875–1.0). A strong signal with poor quality and limited upside drops significantly. A moderate signal with healthy fundamentals and room to run rises. Use this to answer: <em>of the signal candidates, which look more investable from a long-term research perspective?</em></p>
      </div>
    </div>
    <p class="howto-p">The difference is most visible on stocks at the edges — a mega-cap with a great signal but stretched valuation will rank lower on Investor; a mid-cap with solid EPS growth and a healthy chart will rank higher. This is not a recommendation — it is a different prioritization lens on the same data.</p>
  </div>

  <div class="howto-section">
    <div class="howto-h2">Research This Signal — The Explanation Layer</div>
    <p class="howto-p">Click the <b>Research →</b> button on any candidate to open a full research pack. Built entirely from existing data — no AI generation, no buy/sell language. You should be able to understand why a candidate is here in under 30 seconds.</p>
    <div class="metric-grid">

      <div class="metric-card">
        <div class="metric-name">Why This Candidate Is Here</div>
        <div class="metric-abbr">4-line summary at the top of the modal</div>
        <div class="metric-desc">A deterministic summary of: signal strength and validation status, quality check result, opportunity potential status, and the single most important caution pulled from the check data. The SIGNAL label is green for validated, amber for borderline, gray for exploratory. The CAUTION row surfaces the most critical concern.</div>
      </div>

      <div class="metric-card">
        <div class="metric-name">Signal Strength</div>
        <div class="metric-abbr">best signal for this ticker</div>
        <div class="metric-desc">The validated or best-available signal for this ticker: signal name, average alpha vs sector, win rate, number of historical events, p-value, and status. If the signal is exploratory, the summary flags that explicitly.</div>
      </div>

      <div class="metric-card">
        <div class="metric-name">Human Quality Checks</div>
        <div class="metric-abbr">5 checks with pass / warn / fail</div>
        <div class="metric-desc">Each of the five quality checks (liquidity, trend, EPS growth, valuation, market alignment) shown individually with the specific reason. Lets you see exactly which fundamentals are healthy and which need further review.</div>
      </div>

      <div class="metric-card">
        <div class="metric-name">Opportunity Potential</div>
        <div class="metric-abbr">6 checks with scores</div>
        <div class="metric-desc">All six opportunity checks with individual status and reason text. Helps you understand whether this candidate still has potential asymmetric upside or whether the move may already be mature.</div>
      </div>

      <div class="metric-card">
        <div class="metric-name">Context &amp; Wiki</div>
        <div class="metric-abbr">company page freshness</div>
        <div class="metric-desc">Whether a company wiki page exists, when it was last updated and reviewed, and a freshness flag (current / stale / missing). Stale context is flagged — you should verify before relying on it.</div>
      </div>

      <div class="metric-card">
        <div class="metric-name">What To Investigate Next</div>
        <div class="metric-abbr">deterministic checklist</div>
        <div class="metric-desc">A checklist of the most important next research steps, generated from the data state — not a generic list. If the wiki page is stale, it says so. If the price trend is mixed, it flags it. If EPS data is missing, it tells you to check manually. Every item is actionable.</div>
      </div>

    </div>
  </div>

  <div class="howto-section">
    <div class="howto-h2">Direction Modes</div>
    <div class="dir-explainer">
      <div class="dir-card dir-card-long">
        <div class="dir-card-title">Long — 12 months+</div>
        <p>Candidates with the strongest historical signal edge across all three sectors. Ranked by alpha × hit rate × history. Useful for longer research horizons where signal consistency matters most.</p>
      </div>
      <div class="dir-card dir-card-mid">
        <div class="dir-card-title">📈 Mid-term — 1 to 3 Months</div>
        <p>Same signal base, but ranks stocks that win consistently <em>and</em> with low volatility. Divides alpha by standard deviation first — steady results rank above high-average but volatile ones. Look for <b>LOW RISK</b> badges.</p>
      </div>
      <div class="dir-card dir-card-opp">
        <div class="dir-card-title">💎 Opportunity — Pullback Candidates</div>
        <p style="font-size:.76rem;color:var(--text-muted);line-height:1.65">Candidates with a validated edge that are currently trading below their 50-day moving average. Surfaces stocks where signal quality and recent price weakness coincide — worth additional research context. The <b>Discount vs 50d MA</b> column shows how far below the moving average the stock is trading.</p>
      </div>
    </div>
  </div>

  <div class="howto-section">
    <div class="howto-h2">Key Metrics</div>
    <div class="metric-grid">

      <div class="metric-card">
        <div class="metric-name">Alpha vs Sector</div>
        <div class="metric-abbr">stock return − sector ETF return</div>
        <div class="metric-desc"><b>The most important number.</b> If the stock gained 5% and its sector ETF gained 3%, the alpha is +2%. Positive alpha means the stock did something the whole sector didn't — that's the edge we're measuring. Benchmarks: SOXX (AI), ITA (Defense), IYZ (Telecom).</div>
        <span class="metric-good">+1.5% or more = meaningful edge</span>
      </div>

      <div class="metric-card">
        <div class="metric-name">Hit Rate</div>
        <div class="metric-abbr">% of past signal firings that ended in profit</div>
        <div class="metric-desc">Out of every 100 times the signal fired historically, how many ended positive? Above 55% means the pattern wins more often than chance. Above 60% is strong. A high hit rate combined with positive alpha is the best combination — consistent and directional.</div>
        <span class="metric-good">&gt;55% for longs</span>
      </div>

      <div class="metric-card">
        <div class="metric-name">p-value</div>
        <div class="metric-abbr">probability the result is due to chance</div>
        <div class="metric-desc">Less than 0.05 means there is under a 5% chance the alpha is random noise — the signal is <b>validated</b>. Above 0.10 goes to the graveyard. This is the primary filter between real statistical patterns and coincidences.</div>
        <span class="metric-good">&lt;0.05 = validated ✓</span>
        <span class="metric-bad" style="margin-left:.5rem">&gt;0.10 = graveyard</span>
      </div>

      <div class="metric-card">
        <div class="metric-name">Risk Level</div>
        <div class="metric-abbr">standard deviation of past returns</div>
        <div class="metric-desc">How much individual signal results vary from the average. LOW means consistent outcomes; HIGH means wide swings — same average, very different experience. Especially relevant for mid-term research candidates where volatility matters.</div>
        <span class="metric-good" style="display:block">🟢 LOW — under 10% swing</span>
        <span class="metric-bad" style="color:#fbbf24;display:block">🟡 MED — 10–20% swing</span>
        <span class="metric-bad" style="display:block">🔴 HIGH — over 20% swing</span>
      </div>

      <div class="metric-card">
        <div class="metric-name">TA Overlay (optional)</div>
        <div class="metric-abbr">RSI · 50-day MA · 200-day MA</div>
        <div class="metric-desc">Toggle the <b>📊 TA</b> button to add technical context. RSI below 40 indicates oversold conditions. Price above the 50-day MA means short-term uptrend. The TA badge (Bullish / Neutral / Bearish) reflects the overall technical picture. This is a secondary context layer — the signal alpha is the primary input.</div>
        <span class="metric-good">Technical trend supports the signal context</span>
      </div>

    </div>
  </div>

  <div class="howto-section">
    <div class="howto-h2">The Two Validated Signals</div>
    <div class="signal-list">
      <div class="signal-item">
        <div class="signal-item-name">Volume Anomaly ×2.0 — 15d Hold &nbsp;<span class="status-pill pill-validated">validated</span></div>
        <div class="signal-item-desc"><b>What it detects:</b> a stock's 5-day average volume exceeds 2× its 60-day median — something unusual is attracting attention. <b>Historical result:</b> these stocks outperform their sector ETF by ~1.6% over the following 15 trading days, with a 55%+ win rate. Validated on 1,480 events from 2018–2024 (p=0.005), confirmed on fresh 2025–2026 data (Sharpe 1.22). Fires across all three sectors.</div>
      </div>
      <div class="signal-item">
        <div class="signal-item-name">Patent Cluster — Telecom, 45d Hold &nbsp;<span class="status-pill pill-validated">validated</span></div>
        <div class="signal-item-desc"><b>What it detects:</b> a telecom company receives 5 or more patent grants in any 30-day window. <b>Why telecom:</b> telecom companies are IP-licensing businesses — a burst of patents signals an upcoming licensing deal or competitive moat event, which takes ~45 days to be reflected in price. <b>Historical result:</b> these stocks outperform the IYZ telecom ETF by ~1.5% over 45 trading days. Validated on 810 events (p=0.0001). Patent data from PatentsView (USPTO), updated monthly.</div>
      </div>
      <div class="signal-item">
        <div class="signal-item-name">8-K Filing — Excluding Earnings &nbsp;<span class="status-pill pill-borderline">graveyard</span></div>
        <div class="signal-item-desc"><b>What it detects:</b> any major SEC filing that is not an earnings report. <b>Why it failed:</b> showed marginal significance in historical data (p=0.053) but failed to confirm on fresh 2025–2026 data (p=0.27). Not used in the ranking. Logged in the graveyard so it is not retried without a clear refinement hypothesis.</div>
      </div>
    </div>
  </div>

  <div class="howto-section">
    <div class="howto-h2">Methodology Guardrails</div>
    <p class="howto-p"><b>Minimum 30 events required.</b> Fewer than 30 historical firings is not enough data to trust — results are not shown even if the numbers look impressive.</p>
    <p class="howto-p"><b>Out-of-sample holdout.</b> All signals were developed on 2018–2024 data. The 2025–2026 data was kept completely separate and used only once per signal to confirm it still holds on unseen data. This prevents overfitting.</p>
    <p class="howto-p"><b>Transaction cost included.</b> Every backtest trade deducts 0.10% for round-trip costs. Returns shown are net — not paper gains.</p>
    <p class="howto-p"><b>Sector-relative benchmarks.</b> Alpha is measured against the relevant sector ETF (SOXX, ITA, IYZ), not SPY alone. Beating SPY in a bull market for AI stocks is not meaningful edge — beating SOXX is.</p>
    <p class="howto-p"><b>Only recent signals shown.</b> The ranking only includes stocks where the pattern fired in the last 90 days. Historical edge without a recent firing is filtered out.</p>
    <p class="howto-p"><b>This is research, not financial advice.</b> Signals show historical statistical tendencies, not guarantees. Past patterns do not predict future results. Always apply independent judgment before acting on any output.</p>
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
        <p style="font-size:.75rem;color:var(--text-muted);margin-bottom:.6rem">Scaffold missing pages and refresh AUTOGEN sections from DB.</p>
        <button class="success" onclick="runAutogen()" id="autogenBtn">Run Autogen</button>
        <div id="autogen-out" style="margin-top:.6rem;font-size:.75rem;color:var(--text-muted2);white-space:pre-wrap"></div>
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
  if (name === 'top10'     && !_tabLoaded.top10)     { _tabLoaded.top10 = true; loadTop10(); }
  if (name === 'rotation'  && !_tabLoaded.rotation)  { _tabLoaded.rotation = true; loadRotation(); }
  if (name === 'portfolio' && !_tabLoaded.portfolio) { _tabLoaded.portfolio = true; loadPortfolio(); }
  if (name === 'strategic' && !_tabLoaded.strategic) { _tabLoaded.strategic = true; loadStrategicView(); }
  if (name === 'brief'     && !_tabLoaded.brief)     { _tabLoaded.brief = true; loadBrief(); }
}

let _t10Direction = 'long';
function setDirection(dir) {
  _t10Direction = dir;
  document.getElementById('dir-long').className    = 'dir-btn' + (dir === 'long'        ? ' active-long'    : '');
  document.getElementById('dir-midterm').className = 'dir-btn' + (dir === 'midterm'    ? ' active-midterm' : '');
  document.getElementById('dir-opp').className     = 'dir-btn' + (dir === 'opportunity'? ' active-opp'     : '');
  loadTop10();
}

// ── TA overlay ────────────────────────────────────────────────────────────────
let _taEnabled = false;
let _taCache   = null;

function toggleTA() {
  _taEnabled = !_taEnabled;
  const btn = document.getElementById('ta-toggle');
  btn.textContent = '📊 Technical Analysis';
  btn.style.color = _taEnabled ? '#34d399' : '';
  if (_taEnabled) _fetchAndOverlayTA();
  else _clearTA();
}

async function _fetchAndOverlayTA() {
  // Collect tickers currently shown
  const cards = document.querySelectorAll('[data-ta-ticker]');
  if (!cards.length) return;
  const tickers = [...new Set([...cards].map(c => c.dataset.taTicker))].join(',');
  try {
    const data = await (await fetch('/api/ta?tickers=' + encodeURIComponent(tickers))).json();
    _taCache = data;
    _applyTA(data);
  } catch(e) { console.error('TA fetch failed', e); }
}

function _applyTA(data) {
  document.querySelectorAll('[data-ta-ticker]').forEach(el => {
    const ticker = el.dataset.taTicker;
    const ta = data[ticker];
    const existing = el.querySelector('.ta-overlay');
    if (existing) existing.remove();
    if (!ta) return;
    const rsiCls = ta.rsi === null ? 'neu'
      : ta.rsi < 40 ? 'pos' : ta.rsi > 70 ? 'neg' : 'neu';
    const ma50Cls  = ta.pct_vs_50d  === null ? 'neu' : ta.pct_vs_50d  >= 0 ? 'pos' : 'neg';
    const ma200Cls = ta.pct_vs_200d === null ? 'neu' : ta.pct_vs_200d >= 0 ? 'pos' : 'neg';
    const sigCls   = ta.ta_signal === 'bullish' ? 'pos' : ta.ta_signal === 'bearish' ? 'neg' : 'neu';
    const sigLabel = ta.ta_signal === 'bullish' ? '▲ Bullish' : ta.ta_signal === 'bearish' ? '▼ Bearish' : '● Neutral';
    const div = document.createElement('div');
    div.className = 'ta-overlay';
    div.innerHTML =
      `<span class="ta-pill ${sigCls}">${sigLabel}</span>` +
      `<span class="ta-item">RSI <b class="${rsiCls}">${ta.rsi !== null ? ta.rsi : '—'}</b></span>` +
      `<span class="ta-item">50d <b class="${ma50Cls}">${ta.pct_vs_50d !== null ? (ta.pct_vs_50d >= 0 ? '+' : '') + ta.pct_vs_50d + '%' : '—'}</b></span>` +
      `<span class="ta-item">200d <b class="${ma200Cls}">${ta.pct_vs_200d !== null ? (ta.pct_vs_200d >= 0 ? '+' : '') + ta.pct_vs_200d + '%' : '—'}</b></span>`;
    el.appendChild(div);
  });
}

function _clearTA() {
  document.querySelectorAll('.ta-overlay').forEach(el => el.remove());
}

// ── Rotation log ──────────────────────────────────────────────────────────────
async function loadRotation() {
  const dir = document.getElementById('rot-direction').value;
  const card = document.getElementById('rot-card');
  card.innerHTML = '<div class="card-title">Rotation History</div><p class="state-msg">Loading…</p>';
  try {
    const data = await (await fetch('/api/changes?direction=' + dir + '&limit=100')).json();
    renderRotation(data, card);
  } catch(e) {
    card.innerHTML = '<div class="card-title">Rotation History</div>' +
      '<p class="state-msg" style="color:#f87171">Error: ' + escHtml(e.message) + '</p>';
  }
}

function renderRotation(data, card) {
  const rows = data.changes || [];
  const snapshots = data.snapshots || [];
  let html = '<div class="card-title">Rotation History</div>';

  if (!rows.length && !snapshots.length) {
    html += '<p class="state-msg">No rotation data yet — runs after the next signal refresh.</p>';
    card.innerHTML = html;
    return;
  }

  // Group changes by snapshot_date
  const byDate = {};
  rows.forEach(r => {
    (byDate[r.snapshot_date] = byDate[r.snapshot_date] || []).push(r);
  });

  const CHANGE_LABELS = {
    entered:    { icon: '↗', cls: 'pos',  label: 'Entered' },
    exited:     { icon: '↘', cls: 'neg',  label: 'Exited'  },
    moved_up:   { icon: '▲', cls: 'pos',  label: 'Up'      },
    moved_down: { icon: '▼', cls: 'neg',  label: 'Down'    },
  };

  const dates = Object.keys(byDate).sort().reverse();
  if (!dates.length) {
    html += '<p class="state-msg">No changes recorded yet — the list has been stable since the first snapshot.</p>';
    card.innerHTML = html;
    return;
  }

  html += '<div style="overflow-x:auto"><table class="lb-tbl"><thead><tr>' +
    '<th>Date</th><th>Ticker</th><th>Change</th><th>Old Rank</th><th>New Rank</th>' +
    '</tr></thead><tbody>';

  dates.forEach(d => {
    byDate[d].forEach(r => {
      const c = CHANGE_LABELS[r.change_type] || { icon: '?', cls: 'neu', label: r.change_type };
      html += `<tr>
        <td class="neu" style="font-size:.73rem">${escHtml(d)}</td>
        <td class="lb-ticker-cell"><b>${escHtml(r.ticker)}</b></td>
        <td><span class="${c.cls}">${c.icon} ${c.label}</span></td>
        <td class="neu">${r.old_rank !== null ? '#' + r.old_rank : '—'}</td>
        <td class="neu">${r.new_rank !== null ? '#' + r.new_rank : '—'}</td>
      </tr>`;
    });
  });

  html += '</tbody></table></div>';

  // Current snapshot
  if (snapshots.length) {
    html += '<div class="card-title" style="margin-top:1.2rem">Current Top 10 Snapshot</div>' +
      '<div style="overflow-x:auto"><table class="lb-tbl"><thead><tr>' +
      '<th>#</th><th>Ticker</th><th>Alpha</th><th>Last Signal</th><th>N</th>' +
      '</tr></thead><tbody>';
    snapshots.forEach(s => {
      html += `<tr>
        <td class="lb-rank">#${s.rank}</td>
        <td class="lb-ticker-cell"><b>${escHtml(s.ticker)}</b></td>
        <td><span class="${s.avg_alpha >= 0 ? 'pos' : 'neg'}">${s.avg_alpha >= 0 ? '+' : ''}${(s.avg_alpha * 100).toFixed(1)}%</span></td>
        <td class="neu" style="font-size:.73rem">${escHtml(s.last_signal || '—')}</td>
        <td class="neu">${s.n_signals}</td>
      </tr>`;
    });
    html += '</tbody></table></div>';
  }

  card.innerHTML = html;
}

// ── Portfolio Context ─────────────────────────────────────────────────────────
async function loadPortfolio() {
  const el = document.getElementById('ptab-content');
  el.innerHTML = '<p class="state-msg">Loading portfolio context…</p>';
  try {
    const d = await (await fetch('/api/portfolio-context')).json();
    renderPortfolio(d);
  } catch(e) {
    el.innerHTML = '<p class="state-msg">Failed to load portfolio context.</p>';
  }
}

function renderPortfolio(d) {
  const el = document.getElementById('ptab-content');
  const cands = d.candidates || [];
  const rc = d.role_counts || {};
  const rk = d.risk_counts || {};
  const cv = d.conviction_counts || {};
  const tt = d.theme_tickers || {};

  const roleBadge = (r) => `<span class="pc-badge pc-role-${r}" style="margin-right:.25rem">${escHtml(r)} <span style="opacity:.7;font-weight:400">${rc[r]||0}</span></span>`;
  const riskBadge = (r) => `<span class="pc-badge pc-risk-${r}" style="margin-right:.25rem">${escHtml(r)} <span style="opacity:.7;font-weight:400">${rk[r]||0}</span></span>`;
  const convBadge = (r) => `<span class="pc-badge pc-conv-${r}" style="margin-right:.25rem">${escHtml(r)} <span style="opacity:.7;font-weight:400">${cv[r]||0}</span></span>`;

  // Stats row
  let html = `<div class="ptab-stats">
    <div class="ptab-stat-card">
      <div class="ptab-stat-title">Role</div>
      <div class="ptab-dist">
        ${['Core','Growth','Speculative','Watchlist'].map(roleBadge).join('')}
      </div>
    </div>
    <div class="ptab-stat-card">
      <div class="ptab-stat-title">Risk</div>
      <div class="ptab-dist">
        ${['Low','Medium','High'].map(riskBadge).join('')}
      </div>
    </div>
    <div class="ptab-stat-card">
      <div class="ptab-stat-title">Conviction</div>
      <div class="ptab-dist">
        ${['High','Medium','Low'].map(convBadge).join('')}
      </div>
    </div>
    <div class="ptab-stat-card">
      <div class="ptab-stat-title">Coverage</div>
      <div style="font-size:.82rem;color:var(--text-2);margin-top:.1rem">
        <span style="font-weight:700;font-size:1.1rem;color:var(--text)">${cands.length}</span> candidates<br>
        <span style="font-weight:700;font-size:1.1rem;color:var(--text)">${Object.keys(tt).length}</span> themes
      </div>
    </div>
  </div>`;

  // Theme exposure
  const sortedThemes = Object.entries(tt).sort((a,b) => b[1].length - a[1].length);
  if (sortedThemes.length) {
    html += `<div class="card">
      <div class="card-title">Theme Exposure</div>
      <div class="ptab-theme-grid">`;
    for (const [theme, tickers] of sortedThemes) {
      const chips = tickers.map(t =>
        `<span class="ptab-ticker-chip" onclick="openResearch('${escAttr(t)}')">${escHtml(t)}</span>`
      ).join('');
      html += `<div class="ptab-theme-card">
        <div class="ptab-theme-name">${escHtml(theme)} <span style="color:var(--text-muted);font-weight:400">(${tickers.length})</span></div>
        <div class="ptab-theme-tickers">${chips}</div>
      </div>`;
    }
    html += `</div></div>`;
  }

  // Candidate table
  html += `<div class="card">
    <div class="card-title">Top 15 Candidates — Portfolio View</div>
    <table class="ptab-tbl">
      <thead><tr>
        <th>Ticker</th><th>Role</th><th>Risk</th><th>Conviction</th><th>Themes</th><th>Summary</th>
      </tr></thead>
      <tbody>`;
  for (const c of cands) {
    const themes = (c.themes || []).slice(0,3).map(t => `<span class="pc-badge pc-theme" style="font-size:.63rem">${escHtml(t)}</span>`).join(' ');
    html += `<tr>
      <td><button class="ptab-ticker-link" onclick="openResearch('${escAttr(c.ticker)}')">${escHtml(c.ticker)}</button>
          <div style="font-size:.65rem;color:var(--text-muted)">${escHtml(c.name||'')}</div></td>
      <td><span class="pc-badge pc-role-${escAttr(c.role)}">${escHtml(c.role)}</span></td>
      <td><span class="pc-badge pc-risk-${escAttr(c.risk_bucket)}">${escHtml(c.risk_bucket)}</span></td>
      <td>
        <span class="pc-badge pc-conv-${escAttr(c.conviction_level)}">${escHtml(c.conviction_level)}</span>
        <div style="font-size:.63rem;color:var(--text-muted);margin-top:.2rem">${escHtml(c.conviction_reason||'')}</div>
      </td>
      <td>${themes}</td>
      <td style="font-size:.7rem;color:var(--text-muted);max-width:260px">${escHtml(c.summary||'')}</td>
    </tr>`;
  }
  html += `</tbody></table></div>`;

  el.innerHTML = html;
}

// ── Strategic View ────────────────────────────────────────────────────────────
async function loadStrategicView() {
  const el = document.getElementById('strat-content');
  el.innerHTML = '<p class="state-msg">Loading strategic view…</p>';
  try {
    const d = await (await fetch('/api/strategic-view')).json();
    renderStrategicView(d);
  } catch(e) {
    el.innerHTML = '<p class="state-msg">Failed to load strategic view.</p>';
  }
}

function _stratCard(c) {
  const themes = (c.themes || []).slice(0, 3)
    .map(t => `<span class="pc-badge pc-theme" style="font-size:.62rem">${escHtml(t)}</span>`).join('');
  const convCls = `pc-conv-${escAttr(c.conviction_level||'Low')}`;
  const roleCls = `pc-role-${escAttr(c.role||'Growth')}`;
  return `<div class="strat-card">
    <div class="strat-card-hdr">
      <button class="strat-ticker-btn" onclick="openResearch('${escAttr(c.ticker)}')">${escHtml(c.ticker)}</button>
      <span class="pc-badge ${roleCls}" style="font-size:.62rem">${escHtml(c.role||'')}</span>
      <span class="pc-badge ${convCls}" style="font-size:.62rem">${escHtml(c.conviction_level||'')}</span>
    </div>
    <div class="strat-name">${escHtml(c.name||'')}</div>
    ${c.reason ? `<div class="strat-reason">${escHtml(c.reason)}</div>` : ''}
    ${themes ? `<div class="strat-themes">${themes}</div>` : ''}
  </div>`;
}

function _stratCol(key, title, subtitle, items) {
  const cards = items.length
    ? items.map(_stratCard).join('')
    : `<p class="state-msg" style="padding:.5rem 0;text-align:left;font-size:.76rem">No current candidates in this category.</p>`;
  return `<div class="strat-col">
    <div class="strat-col-hdr">
      <div class="strat-col-title ${key}">${escHtml(title)} <span style="font-weight:400;font-size:.7rem;opacity:.7">(${items.length})</span></div>
      <div class="strat-col-subtitle">${escHtml(subtitle)}</div>
    </div>
    ${cards}
  </div>`;
}

function renderStrategicView(d) {
  const el = document.getElementById('strat-content');
  const a  = d.asymmetric   || [];
  const tr = d.transitional || [];
  const cp = d.compounder   || [];
  const sp = d.signal_play  || [];

  let html = `<div class="strat-grid">
    ${_stratCol('asymmetric',   'Asymmetric',   'High uncertainty · high optionality', a)}
    ${_stratCol('transitional', 'Transitional', 'Changing regime · rerating potential', tr)}
    ${_stratCol('compounder',   'Compounder',   'Durable value · recurring economics', cp)}
  </div>`;

  if (sp.length) {
    html += `<div class="card">
      <div class="card-title">Other Signals <span style="font-weight:400;font-size:.72rem;margin-left:.3rem">validated signal · strategic category not yet determined</span></div>
      <div class="strat-signal-row">${sp.map(_stratCard).join('')}</div>
    </div>`;
  }

  el.innerHTML = html;
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
        <div class="drilldown-hdr">Per-event breakdown <span id="dd-count-${s.run_id}" style="color:var(--text-muted2);font-size:.7rem"></span></div>
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
          <span style="font-size:.7rem;color:var(--text-dim)">${evs.length} events</span>
          <span style="font-size:.7rem;color:var(--text-dim)">hit rate <span class="${cls(secAvgRet)}">${returns.length?Math.round(hits/returns.length*100)+'%':'—'}</span></span>
          <span style="font-size:.7rem;color:var(--text-dim)">avg return <span class="${cls(secAvgRet)}">${pct(secAvgRet)}</span></span>
          <span style="font-size:.7rem;color:var(--text-dim)">avg alpha <span class="${cls(secAvgAlpha)}">${pct(secAvgAlpha)}</span></span>
        </div>
        <table class="ev-tbl" style="margin-bottom:.2rem">
          <thead><tr>
            <th>Ticker</th><th>Name</th><th>Event date</th><th>Return</th><th>Alpha</th>
          </tr></thead>
          <tbody>`;

      evs.slice(0, 30).forEach(e => {
        html += `<tr>
          <td><button class="wiki-link" style="font-weight:700;font-size:.78rem" onclick="openWikiPage('wiki/companies/public/${escAttr(e.ticker)}.md')">${escHtml(e.ticker)}</button></td>
          <td style="color:var(--text-dim);font-size:.72rem">${escHtml(e.name ?? '—')}</td>
          <td class="td-mono">${e.event_date ?? '—'}</td>
          <td><span class="${cls(e.net_return)}">${pct(e.net_return)}</span></td>
          <td><span class="${cls(e.alpha_sector)}">${pct(e.alpha_sector)}</span></td>
        </tr>`;
      });
      if (evs.length > 30) html += `<tr><td colspan="5" style="color:var(--text-dim);font-size:.68rem;padding:.3rem .5rem">…and ${evs.length-30} more</td></tr>`;
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

// ── Stock detail modal ────────────────────────────────────────────────────────

function closeStockModal() {
  document.getElementById('stock-modal').classList.remove('open');
}

async function openStockDetail(ticker, name) {
  const modal = document.getElementById('stock-modal');
  document.getElementById('modal-ticker').textContent = ticker;
  document.getElementById('modal-name').textContent = name || '';
  document.getElementById('modal-ta').innerHTML = '<span style="color:var(--text-faint);font-size:.8rem">Loading…</span>';
  document.getElementById('modal-quality').innerHTML = '<span style="color:var(--text-faint);font-size:.8rem">Loading…</span>';
  document.getElementById('modal-ranks').innerHTML = '<span style="color:var(--text-faint);font-size:.8rem">Loading…</span>';
  document.getElementById('modal-signals').innerHTML = '<span style="color:var(--text-faint);font-size:.8rem">Loading…</span>';
  modal.classList.add('open');

  try {
    const r = await fetch(`/api/stock/${encodeURIComponent(ticker)}`);
    const d = await r.json();

    // TA section
    const ta = d.ta;
    if (ta) {
      const taSignalCls = ta.ta_signal === 'bullish' ? 'pos' : ta.ta_signal === 'bearish' ? 'neg' : 'neu';
      document.getElementById('modal-ta').innerHTML =
        `<div class="ta-overlay" style="margin:0">` +
        `<span class="ta-pill ${taSignalCls}">${ta.ta_signal?.toUpperCase() ?? '—'}</span>` +
        `<span class="ta-item">Price <b>$${ta.price ?? '—'}</b></span>` +
        `<span class="ta-item">RSI(14) <b class="${ta.rsi > 70 ? 'neg' : ta.rsi < 30 ? 'pos' : 'neu'}">${ta.rsi ?? '—'}</b></span>` +
        `<span class="ta-item">vs 50d MA <b class="${ta.pct_vs_50d < 0 ? 'pos' : 'neg'}">${ta.pct_vs_50d !== null ? (ta.pct_vs_50d >= 0 ? '+' : '') + ta.pct_vs_50d + '%' : '—'}</b></span>` +
        `<span class="ta-item">vs 200d MA <b class="${ta.pct_vs_200d < 0 ? 'pos' : 'neg'}">${ta.pct_vs_200d !== null ? (ta.pct_vs_200d >= 0 ? '+' : '') + ta.pct_vs_200d + '%' : '—'}</b></span>` +
        `</div>`;
    } else {
      document.getElementById('modal-ta').innerHTML = '<span style="color:var(--text-faint);font-size:.8rem">No TA data available.</span>';
    }

    // Human Quality section
    const hq = d.human_quality || {};
    const hqLabels = {
      liquidity: 'Liquidity', trend: 'Trend',
      eps_growth: 'EPS Growth', valuation: 'Valuation', market_alignment: 'Market Alignment'
    };
    const hqKeys = ['liquidity', 'trend', 'market_alignment', 'eps_growth', 'valuation'];
    let hqHtml = `<div style="font-size:.72rem;color:var(--text-muted);margin-bottom:.5rem">${escHtml(d.human_quality_summary || '')}</div>`;
    hqHtml += hqKeys.map(k => {
      const c = hq[k];
      if (!c) return '';
      const badgeCls = {pass:'hq-pass',warn:'hq-warn',fail:'hq-fail',unknown:'hq-unknown'}[c.status] || 'hq-unknown';
      return `<div style="display:flex;align-items:baseline;gap:.5rem;margin-bottom:.3rem">
        <span class="hq-badge ${badgeCls}" style="min-width:3.2rem;text-align:center">${c.status.toUpperCase()}</span>
        <span style="font-size:.72rem;color:var(--text-muted)"><b style="color:var(--text-2)">${escHtml(hqLabels[k])}</b> — ${escHtml(c.reason)}</span>
      </div>`;
    }).join('');
    if (d.human_quality_score !== null && d.human_quality_score !== undefined) {
      hqHtml += `<div style="font-size:.68rem;color:var(--text-faint);margin-top:.4rem">Quality score: ${(d.human_quality_score * 100).toFixed(0)}/100</div>`;
    }
    document.getElementById('modal-quality').innerHTML = hqHtml;

    // Rank history section
    const ranks = d.rank_history ?? [];
    if (ranks.length) {
      const dirLabel = { long: 'Long', midterm: 'Mid', opportunity: 'Opp' };
      const dirCls   = { long: '', midterm: 'mid', opportunity: 'opp' };
      document.getElementById('modal-ranks').innerHTML = ranks.map(r =>
        `<span class="rank-chip ${dirCls[r.direction] ?? ''}">#${r.rank} ${dirLabel[r.direction] ?? r.direction} · ${r.snapshot_date}</span>`
      ).join('');
    } else {
      document.getElementById('modal-ranks').innerHTML = '<span style="color:var(--text-faint);font-size:.8rem">Not in Top 10 history yet.</span>';
    }

    // Signal history table
    const events = d.events ?? [];
    if (events.length) {
      let tbl = `<div class="lb-tbl-wrap"><table class="lb-tbl"><thead><tr>
        <th>Date</th><th>Signal</th><th>Hold</th><th>Net Return</th><th>Alpha vs Sector</th>
      </tr></thead><tbody>`;
      events.forEach(e => {
        tbl += `<tr>
          <td class="neu">${e.event_date}</td>
          <td style="color:var(--text-muted);font-size:.72rem">${escHtml(_sigLabel(e.signal_name))}</td>
          <td class="neu">${e.hold_days}d</td>
          <td><span class="${e.net_return >= 0 ? 'pos' : 'neg'}">${e.net_return >= 0 ? '+' : ''}${(e.net_return * 100).toFixed(2)}%</span></td>
          <td><span class="${e.alpha_sector >= 0 ? 'pos' : 'neg'}">${e.alpha_sector >= 0 ? '+' : ''}${(e.alpha_sector * 100).toFixed(2)}%</span></td>
        </tr>`;
      });
      tbl += '</tbody></table></div>';
      document.getElementById('modal-signals').innerHTML = tbl;
    } else {
      document.getElementById('modal-signals').innerHTML = '<span style="color:var(--text-faint);font-size:.8rem">No signal events in the last 18 months.</span>';
    }
  } catch(err) {
    document.getElementById('modal-signals').innerHTML = `<span style="color:#f87171;font-size:.8rem">Error loading data: ${escHtml(String(err))}</span>`;
  }
}

// ── Research modal ────────────────────────────────────────────────────────────

function closeResearch() {
  document.getElementById('research-modal').classList.remove('open');
}

function _rsStatusCls(status) {
  return { pass:'rs-pass', warn:'rs-warn', fail:'rs-fail', unknown:'rs-unknown' }[status] || 'rs-unknown';
}
const _SIGNAL_LABELS = {
  'volume_anomaly_5_60_t2.0':                        'Volume Anomaly ×2.0',
  'volume_anomaly_5_60_t2.0__hold5d':                'Volume Anomaly ×2.0 — 5d Hold',
  'volume_anomaly_5_60_t2.0__hold10d':               'Volume Anomaly ×2.0 — 10d Hold',
  'volume_anomaly_5_60_t2.0__hold15d':               'Volume Anomaly ×2.0 — 15d Hold ★',
  'volume_anomaly_5_60_t2.0__hold20d':               'Volume Anomaly ×2.0 — 20d Hold',
  'volume_anomaly_5_60_t2.0__hold30d':               'Volume Anomaly ×2.0 — 30d Hold',
  'volume_anomaly_5_60_t2.0__holdout_10d':           'Volume Anomaly ×2.0 — Holdout 10d',
  'volume_anomaly_5_60_t2.0__holdout_15d':           'Volume Anomaly ×2.0 — Holdout 15d ★',
  'volume_anomaly_5_60_t2.0_ai_infra':               'Volume Anomaly ×2.0 — AI Infra',
  'volume_anomaly_5_60_t2.0_space_defense':          'Volume Anomaly ×2.0 — Space & Defense',
  'volume_anomaly_5_60_t3.0_space_defense':          'Volume Anomaly ×3.0 — Space & Defense',
  'volume_anomaly_5_60_t2.0_defense_excl_speculative':'Volume Anomaly ×2.0 — Defense (excl. speculative)',
  'patent_cluster_telecom_n5_w30d_hold45':           'Patent Cluster — Telecom 45d Hold ★',
  'patent_cluster_n5_w30d':                          'Patent Cluster — All Sectors',
  '8k_excl_earnings':                                '8-K Excl. Earnings',
  '8k_excl_earnings__hold5d':                        '8-K Excl. Earnings — 5d Hold',
  '8k_excl_earnings__hold10d':                       '8-K Excl. Earnings — 10d Hold',
  '8k_excl_earnings__hold15d':                       '8-K Excl. Earnings — 15d Hold',
  '8k_excl_earnings__hold20d':                       '8-K Excl. Earnings — 20d Hold',
  '8k_excl_earnings__hold30d':                       '8-K Excl. Earnings — 30d Hold',
  '8k_excl_earnings__holdout_30d':                   '8-K Excl. Earnings — Holdout 30d',
  '8k_any':                                          '8-K Any Filing',
  '8k_item_1_01':                                    '8-K Item 1.01 — Material Agreement',
  'earnings_surprise_q75':                           'Earnings Surprise Q75',
  'insider_buy_100k':                                'Insider Buy $100k+',
};
function _sigLabel(name) {
  return _SIGNAL_LABELS[name] || name;
}

function _rsBadge(status, label) {
  return `<span class="rs-badge ${_rsStatusCls(status)}">${escHtml(label.toUpperCase())}: ${escHtml((status||'unknown').toUpperCase())}</span>`;
}
function _rsDirChip(dir) {
  const cls = { long:'rs-dir-long', midterm:'rs-dir-midterm', opportunity:'rs-dir-opportunity' }[dir] || '';
  const lbl = { long:'Long', midterm:'Mid-term', opportunity:'Opp' }[dir] || dir;
  return `<span class="rs-dir-chip ${cls}">${escHtml(lbl)}</span>`;
}

async function openResearch(ticker, name) {
  document.getElementById('rs-ticker').textContent = ticker;
  document.getElementById('rs-name').textContent = name || '';
  ['rs-why','rs-portfolio','rs-signal','rs-quality','rs-opportunity','rs-context','rs-history','rs-steps'].forEach(id => {
    document.getElementById(id).innerHTML = '<span style="color:var(--text-faint);font-size:.8rem">Loading…</span>';
  });
  document.getElementById('research-modal').classList.add('open');

  try {
    const d = await (await fetch(`/api/research/${encodeURIComponent(ticker)}`)).json();

    // 0. Why This Candidate Is Here
    const why = d.why_here || {};
    const sigLvlCls = {
      validated:'why-sig-validated', borderline:'why-sig-borderline',
      exploratory:'why-sig-exploratory', none:'why-sig-none'
    }[why.signal_level] || 'why-sig-none';
    document.getElementById('rs-why').innerHTML = `
      <div class="why-grid">
        <div class="why-row">
          <span class="why-label ${sigLvlCls}">SIGNAL</span>
          <span class="why-text">${escHtml(why.signal || '—')}</span>
        </div>
        <div class="why-row">
          <span class="why-label why-label-quality">QUALITY</span>
          <span class="why-text">${escHtml(why.quality || '—')}</span>
        </div>
        <div class="why-row">
          <span class="why-label why-label-opp">OPPORTUNITY</span>
          <span class="why-text">${escHtml(why.opportunity || '—')}</span>
        </div>
        <div class="why-row why-caution-row">
          <span class="why-label why-label-caution">CAUTION</span>
          <span class="why-text">${escHtml(why.main_caution || '—')}</span>
        </div>
      </div>`;

    // 1b. Portfolio Context
    const pc = d.portfolio_context || {};
    if (pc.role) {
      const roleCls = `pc-role-${pc.role}`;
      const riskCls = `pc-risk-${pc.risk_bucket||'Medium'}`;
      const conv    = pc.conviction || {};
      const convCls = `pc-conv-${conv.level||'Low'}`;
      const themes  = (pc.themes || []).map(t => `<span class="pc-badge pc-theme">${escHtml(t)}</span>`).join('');
      const expo    = (pc.exposure_profile || []).map(e => `<span class="pc-badge pc-exposure">${escHtml(e)}</span>`).join('');
      document.getElementById('rs-portfolio').innerHTML = `
        <div class="pc-grid">
          <span><span class="pc-label">ROLE</span><span class="pc-badge ${roleCls}">${escHtml(pc.role)}</span></span>
          <span><span class="pc-label">RISK</span><span class="pc-badge ${riskCls}">${escHtml(pc.risk_bucket||'Medium')}</span></span>
          <span><span class="pc-label">CONVICTION</span><span class="pc-badge ${convCls}">${escHtml(conv.level||'Low')}</span></span>
        </div>
        ${conv.reason ? `<div class="pc-conv-reason">${escHtml(conv.reason)}</div>` : ''}
        ${themes ? `<div style="margin:.4rem 0"><span class="pc-label">THEMES</span>${themes}</div>` : ''}
        ${expo   ? `<div style="margin:.2rem 0"><span class="pc-label">EXPOSURE</span>${expo}</div>` : ''}
        ${pc.summary ? `<div class="pc-summary">${escHtml(pc.summary)}</div>` : ''}`;
    } else {
      document.getElementById('rs-portfolio').innerHTML = '<span style="color:var(--text-faint);font-size:.8rem">Portfolio context unavailable.</span>';
    }

    // 1. Signal Strength
    const sig = d.signal;
    if (sig) {
      const alpha  = sig.alpha  !== null ? `${(sig.alpha*100>=0?'+':'')}${(sig.alpha*100).toFixed(1)}%` : '—';
      const hr     = sig.hit_rate !== null ? Math.round(sig.hit_rate*100)+'%' : '—';
      const pv     = sig.p_value !== null ? sig.p_value.toFixed(3) : '—';
      const stCls  = `rs-signal-status-${sig.status}`;
      document.getElementById('rs-signal').innerHTML = `
        <div class="rs-signal-stat">
          <div class="rs-stat-pill"><b>${escHtml(_sigLabel(sig.name||''))}</b><span>Signal name</span></div>
          <div class="rs-stat-pill"><b class="${sig.alpha!==null?(sig.alpha>=0?'pos':'neg'):'neu'}">${alpha}</b><span>Avg alpha vs sector</span></div>
          <div class="rs-stat-pill"><b class="${sig.hit_rate!==null?(sig.hit_rate>=.5?'pos':'neg'):'neu'}">${hr}</b><span>Win rate</span></div>
          <div class="rs-stat-pill"><b class="neu">${sig.n_events}</b><span>Historical events</span></div>
          <div class="rs-stat-pill"><b class="neu">${pv}</b><span>p-value</span></div>
        </div>
        <div style="margin:.4rem 0"><span class="${stCls}">● ${escHtml(sig.status.toUpperCase())}</span></div>
        <div style="font-size:.78rem;color:var(--text-muted);line-height:1.5">${escHtml(sig.summary)}</div>`;
    } else {
      document.getElementById('rs-signal').innerHTML = '<span style="color:var(--text-faint);font-size:.8rem">No signal data found for this ticker.</span>';
    }

    // 2. Human Quality
    const hq = d.human_quality || {};
    const checks = hq.checks || {};
    const CHECK_LABELS = { liquidity:'Liquidity', trend:'Trend', eps_growth:'EPS Growth', valuation:'Valuation', market_alignment:'Market Alignment' };
    let qHtml = Object.entries(CHECK_LABELS).map(([k, lbl]) => {
      const c = checks[k] || { status:'unknown', reason:'' };
      return `<div style="margin:.3rem 0">
        ${_rsBadge(c.status, lbl)}
        <span style="font-size:.73rem;color:var(--text-2);margin-left:.3rem">${escHtml(c.reason||'')}</span>
      </div>`;
    }).join('');
    if (hq.summary) {
      qHtml += `<div style="font-size:.78rem;color:var(--text-muted);margin-top:.5rem;line-height:1.4">${escHtml(hq.summary)}</div>`;
    }
    document.getElementById('rs-quality').innerHTML = qHtml || '<span style="color:var(--text-faint);font-size:.8rem">No quality data.</span>';

    // 3. Opportunity Potential
    const opp = d.opportunity_potential || {};
    const oppChecks = opp.checks || {};
    const OPP_LABELS = {
      valuation_room:'Valuation Room', growth_support:'Growth Support',
      technical_extension:'Technical Extension', market_cap_asymmetry:'Market Cap',
      sector_tailwind:'Sector Tailwind', risk_penalty:'Risk Penalty',
    };
    const oppStatusCls = { high:'opp-high', medium:'opp-medium', low:'opp-low', unknown:'opp-unknown' };
    let oppHtml = '';
    if (opp.status) {
      oppHtml += `<div style="margin-bottom:.5rem">
        <span class="opp-badge ${oppStatusCls[opp.status]||'opp-unknown'}">${escHtml((opp.status||'unknown').toUpperCase())}</span>
        <span style="font-size:.73rem;color:var(--text-muted);margin-left:.4rem">Opportunity Potential</span>
      </div>`;
    }
    oppHtml += Object.entries(OPP_LABELS).map(([k, lbl]) => {
      const c = oppChecks[k] || { status:'unknown', reason:'' };
      return `<div style="margin:.3rem 0">
        ${_rsBadge(c.status, lbl)}
        <span style="font-size:.73rem;color:var(--text-2);margin-left:.3rem">${escHtml(c.reason||'')}</span>
      </div>`;
    }).join('');
    if (opp.summary) {
      oppHtml += `<div style="font-size:.78rem;color:var(--text-muted);margin-top:.5rem;line-height:1.4">${escHtml(opp.summary)}</div>`;
    }
    document.getElementById('rs-opportunity').innerHTML = oppHtml || '<span style="color:var(--text-faint);font-size:.8rem">No opportunity data.</span>';

    // 4. Context Status
    const ctx = d.context || {};
    const freshCls = { current:'rs-fresh', stale:'rs-stale', missing:'rs-missing' }[ctx.freshness_status] || 'rs-missing';
    document.getElementById('rs-context').innerHTML = `
      <div style="font-size:.8rem;line-height:1.8">
        <div><b>Company page:</b> ${ctx.has_company_page
          ? `<a href="#" onclick="event.preventDefault();openWikiPage('${escAttr(ctx.company_page||'')}');closeResearch();" style="color:#a5b4fc">${escHtml(ctx.company_page||'')}</a>`
          : '<span style="color:var(--text-faint)">Not yet created</span>'}</div>
        <div><b>Freshness:</b> <span class="rs-badge ${freshCls}">${escHtml((ctx.freshness_status||'missing').toUpperCase())}</span></div>
        ${ctx.last_updated ? `<div><b>Last updated:</b> <span style="color:var(--text-muted)">${escHtml(ctx.last_updated)}</span></div>` : ''}
        ${ctx.last_reviewed ? `<div><b>Last reviewed:</b> <span style="color:var(--text-muted)">${escHtml(ctx.last_reviewed)}</span></div>` : ''}
        ${ctx.freshness_status === 'stale' ? '<div style="color:#fbbf24;margin-top:.3rem;font-size:.75rem">⚠ Context is stale — verify before relying on this candidate.</div>' : ''}
      </div>`;

    // 5. Recent Appearances
    const appearances = (d.history || {}).recent_appearances || [];
    if (appearances.length) {
      document.getElementById('rs-history').innerHTML = appearances.map(a =>
        `<div class="rs-history-row">${_rsDirChip(a.direction)}<b>#${a.rank}</b> on ${escHtml(a.date)}</div>`
      ).join('');
    } else {
      document.getElementById('rs-history').innerHTML = '<span style="color:var(--text-faint);font-size:.8rem">Not yet in ranking snapshots.</span>';
    }

    // 6. Next Steps
    const steps = d.next_steps || [];
    document.getElementById('rs-steps').innerHTML = steps.length
      ? `<ul class="rs-steps">${steps.map(s => `<li>${escHtml(s)}</li>`).join('')}</ul>`
      : '<span style="color:var(--text-faint);font-size:.8rem">No steps available.</span>';

  } catch(err) {
    ['rs-portfolio','rs-signal','rs-quality','rs-opportunity','rs-context','rs-history','rs-steps'].forEach(id => {
      document.getElementById(id).innerHTML = `<span style="color:#f87171;font-size:.8rem">Error: ${escHtml(String(err))}</span>`;
    });
  }
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
  const sig     = document.getElementById('t10-signal').value;
  const sec     = document.getElementById('t10-sector').value;
  const score   = document.getElementById('t10-score').value;
  const dir     = _t10Direction;
  const recency = document.getElementById('t10-recency').value;
  document.getElementById('t10-podium').innerHTML =
    '<p class="state-msg" style="grid-column:1/-1">Loading…</p>';
  document.getElementById('t10-board').innerHTML =
    '<div class="card-title">Leaderboard</div><p class="state-msg">Loading…</p>';
  try {
    const base    = { signal_filter: sig, sector: sec, score_by: score, recency_days: recency, limit: 10 };
    const podBase = { signal_filter: sig, sector: sec, score_by: score, recency_days: recency, limit: 3 };
    const mkUrl   = (d, b = base) => '/top10?' + new URLSearchParams({ ...b, direction: d });
    // Fetch current direction (top 10) + podium of all three modes (top 3) in parallel
    const [data, rLong, rMid, rOpp] = await Promise.all([
      fetch(mkUrl(dir)).then(r => r.json()),
      fetch(mkUrl('long',        podBase)).then(r => r.json()).catch(() => ({ stocks: [] })),
      fetch(mkUrl('midterm',     podBase)).then(r => r.json()).catch(() => ({ stocks: [] })),
      fetch(mkUrl('opportunity', podBase)).then(r => r.json()).catch(() => ({ stocks: [] })),
    ]);
    const inLong = new Set((rLong.stocks || []).map(s => s.ticker));
    const inMid  = new Set((rMid.stocks  || []).map(s => s.ticker));
    const inOpp  = new Set((rOpp.stocks  || []).map(s => s.ticker));
    const allModes = new Set([...inLong].filter(t => inMid.has(t) && inOpp.has(t)));
    renderTop10(data, allModes);
  } catch(e) {
    document.getElementById('t10-podium').innerHTML = '';
    document.getElementById('t10-board').innerHTML =
      '<div class="card-title">Leaderboard</div><p class="state-msg" style="color:#f87171">Error: ' +
      escHtml(e.message) + '</p>';
  }
}

function _hqBadge(status, label) {
  const cls = { pass:'hq-pass', warn:'hq-warn', fail:'hq-fail', unknown:'hq-unknown' }[status] || 'hq-unknown';
  return `<span class="hq-badge ${cls}" title="${escAttr(label)}">${escHtml(label)}</span>`;
}
function _oppBadge(status) {
  if (!status) return '';
  const CLS = { high:'opp-high', medium:'opp-medium', low:'opp-low', unknown:'opp-unknown' };
  const LBL = { high:'OPP: HIGH', medium:'OPP: MED', low:'OPP: LOW', unknown:'OPP: —' };
  return `<span class="opp-badge ${CLS[status]||'opp-unknown'}" title="Opportunity Potential: ${status.toUpperCase()}">${LBL[status]||'OPP: —'}</span>`;
}

function _hqRow(hq) {
  if (!hq) return '';
  const LIQ = hq.liquidity,  TRD = hq.trend,  MKT = hq.market_alignment;
  if (!LIQ && !TRD && !MKT) return '';
  return `<div class="hq-row">` +
    (LIQ ? _hqBadge(LIQ.status, 'LIQ') : '') +
    (TRD ? _hqBadge(TRD.status, 'TRD') : '') +
    (MKT ? _hqBadge(MKT.status, 'MKT') : '') +
  `</div>`;
}

function renderTop10(data, allModes = new Set()) {
  const stocks    = data.stocks || [];
  const isOpp     = data.direction === 'opportunity';
  const isMidterm = data.direction === 'midterm';
  const scoreKey  = isOpp ? 'opp_score' : isMidterm ? 'midterm_score'
    : (['blended','investor'].includes(data.score_by) ? 'composite_score' : (data.score_by || 'composite_score'));
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
  const OPP_MEDALS     = ['💎','💎','💎'];
  const MIDTERM_MEDALS = ['🏅','🏅','🏅'];
  const LONG_RANK_CLS    = ['rank-1','rank-2','rank-3'];
  const OPP_RANK_CLS     = ['opp-rank-1','opp-rank-2','opp-rank-3'];
  const MIDTERM_RANK_CLS = ['mt-rank-1','mt-rank-2','mt-rank-3'];
  const MEDALS   = isOpp ? OPP_MEDALS   : isMidterm ? MIDTERM_MEDALS : LONG_MEDALS;
  const RANK_CLS = isOpp ? OPP_RANK_CLS : isMidterm ? MIDTERM_RANK_CLS : LONG_RANK_CLS;

  // ── Podium (top 3) ──────────────────────────────────────────────────────────
  const podiumEl = document.getElementById('t10-podium');
  const emptyMsg = isOpp     ? 'No opportunity candidates found — try extending the recency window or relaxing the signal filter.'
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
    const hrVal    = s.hit_rate;
    const hrDisp   = hrVal !== null ? Math.round(hrVal * 100) + '%' : '—';
    const hrCls    = hrVal !== null ? (hrVal >= 0.5 ? 'pos' : 'neg') : 'neu';
    const hrLabel  = 'Hit rate';
    const alphaLabel = 'Alpha';
    const discountDisp = isOpp && s.pct_vs_50d !== null
      ? `<div class="stat-item"><span class="stat-label">Discount vs 50d MA</span><span class="stat-val ${s.pct_vs_50d < 0 ? 'pos' : 'neg'}">${s.pct_vs_50d >= 0 ? '+' : ''}${s.pct_vs_50d}%</span></div>` : '';

    // Volatility display for mid-term
    const volPct  = s.std_return !== null ? Math.round(s.std_return * 100) + '%' : '—';
    const volCls  = s.std_return === null ? 'neu'
      : s.std_return < 0.10 ? 'vol-low' : s.std_return < 0.20 ? 'vol-med' : 'vol-high';

    const extraStat = isMidterm
      ? `<div class="stat-item"><span class="stat-label">Volatility</span><span class="stat-val ${volCls}">${volPct}</span></div>`
      : `<div class="stat-item"><span class="stat-label">Avg return</span><span class="stat-val ${cls(s.avg_return)}">${pct(s.avg_return)}</span></div>`;

    const allModeBadge = allModes.has(s.ticker)
      ? `<span class="all-modes-badge" title="Ranks in Long, Mid-term & Opportunity">★ All modes</span>` : '';
    return `
    <div class="podium-card ${RANK_CLS[i]}" data-ta-ticker="${escAttr(s.ticker)}"
         onclick="openStockDetail('${escAttr(s.ticker)}','${escAttr(s.name||'')}')">
      <div class="podium-medal">${MEDALS[i]}</div>
      <div class="podium-ticker">${escHtml(s.ticker)}</div>
      <div class="podium-company">${escHtml(s.name || '')} ${allModeBadge}</div>
      <div style="display:flex;gap:.35rem;flex-wrap:wrap;align-items:center">${sectorBadge(s.sector)}${riskBadge(s.std_return)}</div>
      <div class="podium-stats">
        <div class="stat-item"><span class="stat-label">Signals</span><span class="stat-val neu">${s.n_signals}</span></div>
        <div class="stat-item"><span class="stat-label">${alphaLabel}</span><span class="stat-val ${cls(s.avg_alpha)}">${pct(s.avg_alpha)}</span></div>
        <div class="stat-item"><span class="stat-label">${hrLabel}</span><span class="stat-val ${hrCls}">${hrDisp}</span></div>
        ${extraStat}
        <div class="stat-item"><span class="stat-label">Last signal</span><span class="stat-val neu" style="font-size:.72rem">${s.last_signal || '—'}</span></div>
        ${discountDisp}
      </div>
      ${_hqRow(s.human_quality)}
      <div style="margin:.25rem 0">${_oppBadge(s.opportunity_status)}</div>
      <div class="score-bar-wrap">
        <div class="score-bar-fill" style="width:${barPct}%"></div>
      </div>
      <div style="display:flex;gap:.4rem;margin-top:.45rem;flex-wrap:wrap">
        <button class="wiki-link" style="font-size:.76rem"
          onclick="event.stopPropagation();openWikiPage('${escAttr(wiki)}')">View company wiki →</button>
        <button class="research-btn"
          onclick="event.stopPropagation();openResearch('${escAttr(s.ticker)}','${escAttr(s.name||'')}')">Research →</button>
      </div>
    </div>`;
  }).join('');

  // ── Leaderboard (#4–10) ─────────────────────────────────────────────────────
  const rest    = stocks.slice(3);
  const boardEl = document.getElementById('t10-board');
  const isInvestor = data.score_by === 'investor';
  const boardTitle = isOpp      ? `Pullback Candidates — #4 to #${stocks.length}`
    : isMidterm  ? `Mid-term Candidates (1–3 months, lower volatility) — #4 to #${stocks.length}`
    : isInvestor ? `Investor Candidates — #4 to #${stocks.length}`
    : `Research Candidates — #4 to #${stocks.length}`;

  if (!rest.length) {
    boardEl.innerHTML = `<div class="card-title">${boardTitle}</div>` +
      '<p class="state-msg">Only ' + stocks.length + ' stock(s) matched the current filters.</p>';
    return;
  }

  const alphaHdr = isMidterm ? 'Alpha vs Sector' : 'Avg Alpha';
  const hrHdr    = 'Hit Rate';
  const retHdr   = isMidterm ? 'Volatility' : isOpp ? 'Discount vs 50d MA' : 'Avg Return';
  const barClass = isOpp ? 'lb-bar-fill opp' : isMidterm ? 'lb-bar-fill midterm' : 'lb-bar-fill';

  let html = `<div class="card-title">${boardTitle}</div>
    <div class="lb-tbl-wrap"><table class="lb-tbl"><thead><tr>
      <th class="lb-rank">#</th>
      <th>Ticker</th><th>Company</th><th>Sector</th>
      <th>Signals</th><th>${alphaHdr}</th><th>${hrHdr}</th><th>${retHdr}</th>
      <th>Last Signal</th><th>Quality</th><th>Opportunity</th><th class="lb-bar-cell">Score</th>
    </tr></thead><tbody>`;

  rest.forEach((s, i) => {
    const score   = s[scoreKey] ?? 0;
    const barPct  = maxScore > 0 ? (score / maxScore * 100).toFixed(1) : 0;
    const hrVal   = s.hit_rate;
    const hrDisp  = hrVal !== null ? Math.round(hrVal * 100) + '%' : '—';
    const hrCls   = hrVal !== null ? (hrVal >= 0.5 ? 'pos' : 'neg') : 'neu';
    const wiki    = `wiki/companies/public/${s.ticker}.md`;
    // Opportunity: show discount vs 50d MA; Mid-term: show volatility; else avg return
    const retVal  = isOpp
      ? (s.pct_vs_50d !== null
          ? `<span class="${s.pct_vs_50d < 0 ? 'pos' : 'neg'}">${s.pct_vs_50d >= 0 ? '+' : ''}${s.pct_vs_50d}%</span>`
          : '<span class="neu">—</span>')
      : isMidterm
        ? `<span class="${s.std_return === null ? 'neu' : s.std_return < 0.10 ? 'vol-low' : s.std_return < 0.20 ? 'vol-med' : 'vol-high'}">${s.std_return !== null ? Math.round(s.std_return * 100) + '%' : '—'}</span>`
        : `<span class="${cls(s.avg_return)}">${pct(s.avg_return)}</span>`;
    const lbAllMode = allModes.has(s.ticker)
      ? `<span class="all-modes-badge" title="Ranks in Long, Mid-term & Opportunity">★ All modes</span>` : '';
    html += `<tr onclick="openStockDetail('${escAttr(s.ticker)}','${escAttr(s.name||'')}')">
      <td class="lb-rank">${i + 4}</td>
      <td class="lb-ticker-cell">
        ${escHtml(s.ticker)} ${riskBadge(s.std_return)} ${lbAllMode}
        <button class="research-btn" style="display:block;margin-top:.25rem"
          onclick="event.stopPropagation();openResearch('${escAttr(s.ticker)}','${escAttr(s.name||'')}')">Research →</button>
      </td>
      <td style="color:var(--text-muted);font-size:.75rem">${escHtml(s.name || '—')}</td>
      <td>${sectorBadge(s.sector)}</td>
      <td class="neu">${s.n_signals}</td>
      <td><span class="${cls(s.avg_alpha)}">${pct(s.avg_alpha)}</span></td>
      <td><span class="${hrCls}">${hrDisp}</span></td>
      <td>${retVal}</td>
      <td class="neu" style="font-size:.73rem">${s.last_signal || '—'}</td>
      <td>${_hqRow(s.human_quality)}</td>
      <td>${_oppBadge(s.opportunity_status)}</td>
      <td class="lb-bar-cell">
        <div class="lb-bar"><div class="${barClass}" style="width:${barPct}%"></div></div>
      </td>
    </tr>`;
  });
  html += '</tbody></table></div>';
  boardEl.innerHTML = html;

  // Re-apply TA overlay if it was enabled before refresh
  if (_taEnabled) _fetchAndOverlayTA();
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

// ── Theme toggle ─────────────────────────────────────────────────────────────
function toggleTheme() {
  const isLight = document.body.classList.toggle('light');
  localStorage.setItem('sa-theme', isLight ? 'light' : 'dark');
  document.getElementById('theme-btn').textContent = isLight ? '🌙 Dark' : '☀ Light';
}
(function() {
  if (localStorage.getItem('sa-theme') === 'light') {
    document.body.classList.add('light');
    document.getElementById('theme-btn').textContent = '🌙 Dark';
  }
})();

// Boot
loadTop10();
loadPages();
</script>

<!-- ═══════════════════════ STOCK DETAIL MODAL -->
<div class="modal-backdrop" id="stock-modal" onclick="if(event.target===this)closeStockModal()">
  <div class="modal-box">
    <button class="modal-close" onclick="closeStockModal()">✕</button>
    <div class="modal-ticker" id="modal-ticker"></div>
    <div class="modal-name" id="modal-name"></div>

    <div class="modal-section" id="modal-ta-section">
      <div class="modal-section-title">Technical Analysis</div>
      <div id="modal-ta"></div>
    </div>

    <div class="modal-section">
      <div class="modal-section-title">Research Quality Filters</div>
      <div id="modal-quality"><span style="color:var(--text-faint);font-size:.8rem">Loading…</span></div>
    </div>

    <div class="modal-section" id="modal-ranks-section">
      <div class="modal-section-title">Past Rankings</div>
      <div id="modal-ranks"></div>
    </div>

    <div class="modal-section">
      <div class="modal-section-title">Signal History — last 18 months</div>
      <div id="modal-signals"></div>
    </div>
  </div>
</div>

<!-- ═══════════════════════ RESEARCH MODAL -->
<div class="modal-backdrop" id="research-modal" onclick="if(event.target===this)closeResearch()">
  <div class="modal-box">
    <button class="modal-close" onclick="closeResearch()">✕</button>
    <div class="modal-ticker" id="rs-ticker"></div>
    <div class="modal-name" id="rs-name" style="margin-bottom:.6rem"></div>
    <div style="font-size:.68rem;color:#a5b4fc;font-weight:700;letter-spacing:.06em;margin-bottom:.8rem">
      TOP RESEARCH CANDIDATE
    </div>

    <div class="modal-section">
      <div class="modal-section-title">Why This Candidate Is Here</div>
      <div id="rs-why"><span style="color:var(--text-faint);font-size:.8rem">Loading…</span></div>
    </div>

    <div class="modal-section">
      <div class="modal-section-title">Portfolio Context</div>
      <div id="rs-portfolio"><span style="color:var(--text-faint);font-size:.8rem">Loading…</span></div>
    </div>

    <div class="modal-section" id="rs-signal-section">
      <div class="modal-section-title">Signal Strength</div>
      <div id="rs-signal"><span style="color:var(--text-faint);font-size:.8rem">Loading…</span></div>
    </div>

    <div class="modal-section">
      <div class="modal-section-title">Human Quality Checks</div>
      <div id="rs-quality"><span style="color:var(--text-faint);font-size:.8rem">Loading…</span></div>
    </div>

    <div class="modal-section">
      <div class="modal-section-title">Opportunity Potential</div>
      <div id="rs-opportunity"><span style="color:var(--text-faint);font-size:.8rem">Loading…</span></div>
    </div>

    <div class="modal-section">
      <div class="modal-section-title">Context Status</div>
      <div id="rs-context"><span style="color:var(--text-faint);font-size:.8rem">Loading…</span></div>
    </div>

    <div class="modal-section">
      <div class="modal-section-title">Recent Appearances</div>
      <div id="rs-history"><span style="color:var(--text-faint);font-size:.8rem">Loading…</span></div>
    </div>

    <div class="modal-section">
      <div class="modal-section-title">What To Investigate Next</div>
      <div id="rs-steps"><span style="color:var(--text-faint);font-size:.8rem">Loading…</span></div>
    </div>
  </div>
</div>

<!-- ═══════════════════════ DISCLAIMER -->
<div class="disclaimer-bar">
  Not financial advice. SignalAlpha surfaces historical statistical patterns only.
  Past edge does not guarantee future results. All results are backtested and may not reflect live trading conditions.
  Always apply your own judgment before acting on any output.
</div>

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


@app.get("/api/stock/{ticker}")
async def stock_detail(ticker: str):
    """Return signal history (18m), TA, and rank history for a single ticker."""
    ticker = ticker.upper()
    db = _open_db()
    try:
        # Signal events last 18 months across all validated runs
        event_rows = db.execute("""
            SELECT se.event_date, sr.signal_name,
                   (se.exit_date - se.entry_date) AS hold_days,
                   se.net_return, se.alpha_sector
            FROM signal_events se
            JOIN signal_runs sr ON sr.run_id = se.run_id
            JOIN (SELECT signal_name, MAX(run_id) AS latest_run_id
                  FROM signal_runs GROUP BY signal_name) lr
              ON lr.signal_name = sr.signal_name AND lr.latest_run_id = sr.run_id
            WHERE se.ticker = ?
              AND se.event_date >= CURRENT_DATE - INTERVAL '18 months'
            ORDER BY se.event_date DESC
            LIMIT 100
        """, [ticker]).fetchall()

        events = []
        for r in event_rows:
            events.append({
                "event_date":   str(r[0])[:10] if r[0] else None,
                "signal_name":  r[1],
                "hold_days":    r[2],
                "net_return":   round(float(r[3]), 4) if r[3] is not None else None,
                "alpha_sector": round(float(r[4]), 4) if r[4] is not None else None,
            })

        # Rank history from snapshots
        tables = {r[0] for r in db.execute("SHOW TABLES").fetchall()}
        rank_history = []
        if "top10_snapshots" in tables:
            rank_rows = db.execute("""
                SELECT direction, rank, snapshot_date
                FROM top10_snapshots
                WHERE ticker = ?
                ORDER BY snapshot_date DESC
                LIMIT 30
            """, [ticker]).fetchall()
            rank_history = [
                {"direction": r[0], "rank": r[1], "snapshot_date": str(r[2])[:10]}
                for r in rank_rows
            ]

        # TA
        ta = _compute_ta([ticker]).get(ticker)

        # Human quality
        sector_row = db.execute("SELECT sector FROM universe WHERE ticker = ?", [ticker]).fetchone()
        sector = sector_row[0] if sector_row else None
        quality = evaluate_human_quality_batch(db, [ticker], {ticker: sector or ""})
        hq = quality.get(ticker, {})

        return JSONResponse({
            "ticker": ticker,
            "events": events,
            "rank_history": rank_history,
            "ta": ta,
            "human_quality": hq.get("checks", {}),
            "human_quality_score": hq.get("score"),
            "human_quality_summary": hq.get("summary", ""),
        })
    finally:
        db.close()


@app.get("/top10")
async def top10_endpoint(
    signal_filter: str = Query("validated"),
    sector: str = Query("all"),
    score_by: str = Query("composite"),
    direction: str = Query("long"),
    limit: int = Query(10),
    recency_days: int = Query(90),
):
    if signal_filter not in VALID_FILTERS:
        signal_filter = "validated"
    if sector not in VALID_SECTORS:
        sector = "all"
    if score_by not in VALID_SCORE:
        score_by = "composite"
    if direction not in VALID_DIRECTION:
        direction = "long"
    if recency_days < 0:
        recency_days = 90

    db = _open_db()
    try:
        stocks, order_col = fetch_rankings(
            db,
            signal_filter=signal_filter,
            sector=sector,
            direction=direction,
            score_by=score_by,
            recency_days=recency_days,
            limit=limit,
        )
        sector_map = {s["ticker"]: s["sector"] for s in stocks}
        quality    = evaluate_human_quality_batch(db, [s["ticker"] for s in stocks], sector_map)
        for s in stocks:
            q = quality.get(s["ticker"], {})
            hq_score = q.get("score") or 0.5
            s["human_quality_score"]   = hq_score
            s["human_quality"]         = q.get("checks", {})
            s["human_quality_summary"] = q.get("summary", "")
            # Quality multiplier: narrow range for standard modes, wide for investor
            q_base   = 0.4  if score_by == "investor" else 0.75
            q_range  = 0.6  if score_by == "investor" else 0.25
            multiplier = q_base + q_range * hq_score
            for col in ("composite_score", "midterm_score", "opp_score"):
                if s.get(col) is not None:
                    s[col] = round(s[col] * multiplier, 6)

        stocks.sort(key=lambda s: s.get(order_col) or 0, reverse=True)

        # Opportunity potential — always computed; also used as a ranking multiplier
        # for blended (narrow range) and investor (wide range) modes
        hq_map = {s["ticker"]: {"checks": s["human_quality"]} for s in stocks}
        opp    = evaluate_opportunity_batch(db, [s["ticker"] for s in stocks], sector_map,
                                            human_quality_map=hq_map)
        for s in stocks:
            o = opp.get(s["ticker"], {})
            s["opportunity_score"]   = o.get("score")
            s["opportunity_status"]  = o.get("status")
            s["opportunity_summary"] = o.get("summary", "")
            s["opportunity"]         = o.get("checks", {})

        if score_by in ("blended", "investor"):
            o_base  = 0.4  if score_by == "investor" else 0.75
            o_range = 0.6  if score_by == "investor" else 0.25
            for s in stocks:
                opp_mult = o_base + o_range * (s.get("opportunity_score") or 0.5)
                for col in ("composite_score", "midterm_score", "opp_score"):
                    if s.get(col) is not None:
                        s[col] = round(s[col] * opp_mult, 6)
            stocks.sort(key=lambda s: s.get(order_col) or 0, reverse=True)

        return JSONResponse({
            "score_by": score_by if score_by in ("blended", "investor") else order_col,
            "direction": direction,
            "signal_filter": signal_filter,
            "sector": sector,
            "stocks": stocks,
        })
    finally:
        db.close()


# ── Technical Analysis ────────────────────────────────────────────────────────

def _compute_ta(tickers: list[str]) -> dict:
    """Compute RSI(14), SMA50, SMA200 for each ticker from prices table."""
    db = _open_db()
    results = {}
    try:
        for ticker in tickers:
            rows = db.execute(
                "SELECT close FROM prices WHERE ticker = ? ORDER BY date DESC LIMIT 250",
                [ticker],
            ).fetchall()
            if len(rows) < 20:
                results[ticker] = None
                continue

            closes = [r[0] for r in reversed(rows)]
            deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
            gains  = [max(d, 0) for d in deltas]
            losses = [max(-d, 0) for d in deltas]

            period = 14
            if len(gains) >= period:
                avg_gain = sum(gains[-period:]) / period
                avg_loss = sum(losses[-period:]) / period
                rsi = 100.0 if avg_loss == 0 else round(100 - 100 / (1 + avg_gain / avg_loss), 1)
            else:
                rsi = None

            current  = closes[-1]
            sma50    = sum(closes[-50:])  / min(50, len(closes))  if len(closes) >= 10 else None
            sma200   = sum(closes[-200:]) / min(200, len(closes)) if len(closes) >= 50 else None
            pct50    = round((current / sma50  - 1) * 100, 1) if sma50  else None
            pct200   = round((current / sma200 - 1) * 100, 1) if sma200 else None

            bull = sum([
                rsi is not None and rsi < 60,
                pct50  is not None and pct50  > 0,
                pct200 is not None and pct200 > 0,
            ])
            bear = sum([
                rsi is not None and rsi > 70,
                pct50  is not None and pct50  < 0,
                pct200 is not None and pct200 < 0,
            ])
            ta_signal = "bullish" if bull >= 2 else "bearish" if bear >= 2 else "neutral"

            results[ticker] = {
                "rsi":         rsi,
                "pct_vs_50d":  pct50,
                "pct_vs_200d": pct200,
                "ta_signal":   ta_signal,
                "price":       round(current, 2),
            }
    finally:
        db.close()
    return results


@app.get("/api/ta")
async def ta_endpoint(tickers: str = Query(...)):
    """Return TA indicators (RSI14, SMA50, SMA200) for a comma-separated list of tickers."""
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()][:20]
    return JSONResponse(_compute_ta(ticker_list))


@app.get("/api/research/{ticker}")
async def research_endpoint(ticker: str):
    """Return a deterministic research pack for a single ticker."""
    ticker = ticker.upper()
    db = _open_db()
    try:
        result = build_research(db, ticker, WIKI_ROOT)
        return JSONResponse(result)
    finally:
        db.close()


# ── Portfolio context (aggregated top-15 view) ────────────────────────────────

@app.get("/api/portfolio-context")
async def portfolio_context_endpoint():
    db = _open_db()
    try:
        stocks, _ = fetch_rankings(
            db, signal_filter="validated", sector="all",
            direction="long", score_by="composite",
            recency_days=90, limit=15,
        )
        tickers     = [s["ticker"] for s in stocks]
        sector_map  = {s["ticker"]: s.get("sector") or "" for s in stocks}
        name_map    = {s["ticker"]: s.get("name") or s["ticker"] for s in stocks}
        quality     = evaluate_human_quality_batch(db, tickers, sector_map)
        hq_map      = {t: {"score": quality.get(t, {}).get("score"),
                           "checks": quality.get(t, {}).get("checks", {})}
                       for t in tickers}
        opp_map     = evaluate_opportunity_batch(db, tickers, sector_map,
                                                 human_quality_map=hq_map)

        candidates: list[dict] = []
        theme_tickers: dict[str, list[str]] = {}
        role_counts       = {"Core": 0, "Growth": 0, "Speculative": 0, "Watchlist": 0}
        risk_counts       = {"Low": 0, "Medium": 0, "High": 0}
        conviction_counts = {"High": 0, "Medium": 0, "Low": 0}

        for ticker in tickers:
            hq  = quality.get(ticker, {})
            opp = opp_map.get(ticker, {})
            pc  = build_portfolio_context(
                ticker=ticker,
                sector=sector_map[ticker],
                signal_data={"status": "validated"},
                human_quality=hq,
                opportunity=opp,
            )
            candidates.append({
                "ticker":           ticker,
                "name":             name_map[ticker],
                "sector":           sector_map[ticker],
                "role":             pc["role"],
                "risk_bucket":      pc["risk_bucket"],
                "conviction_level": pc["conviction"]["level"],
                "conviction_reason": pc["conviction"]["reason"],
                "themes":           pc["themes"],
                "exposure_profile": pc["exposure_profile"],
                "summary":          pc["summary"],
            })
            role_counts[pc["role"]]                     = role_counts.get(pc["role"], 0) + 1
            risk_counts[pc["risk_bucket"]]               = risk_counts.get(pc["risk_bucket"], 0) + 1
            conviction_counts[pc["conviction"]["level"]] = conviction_counts.get(pc["conviction"]["level"], 0) + 1
            for theme in pc["themes"]:
                theme_tickers.setdefault(theme, []).append(ticker)

        return JSONResponse({
            "candidates":        candidates,
            "theme_tickers":     theme_tickers,
            "role_counts":       role_counts,
            "risk_counts":       risk_counts,
            "conviction_counts": conviction_counts,
        })
    finally:
        db.close()


# ── Strategic view (aggregated top-15 classification) ─────────────────────────

@app.get("/api/strategic-view")
async def strategic_view_endpoint():
    db = _open_db()
    try:
        stocks, _ = fetch_rankings(
            db, signal_filter="validated", sector="all",
            direction="long", score_by="composite",
            recency_days=90, limit=15,
        )
        tickers    = [s["ticker"] for s in stocks]
        sector_map = {s["ticker"]: s.get("sector") or "" for s in stocks}
        name_map   = {s["ticker"]: s.get("name") or s["ticker"] for s in stocks}
        quality    = evaluate_human_quality_batch(db, tickers, sector_map)
        hq_map     = {t: {"score": quality.get(t, {}).get("score"),
                          "checks": quality.get(t, {}).get("checks", {})}
                      for t in tickers}
        opp_map    = evaluate_opportunity_batch(db, tickers, sector_map,
                                                human_quality_map=hq_map)

        candidates: list[dict] = []
        for ticker in tickers:
            hq  = quality.get(ticker, {})
            opp = opp_map.get(ticker, {})
            pc  = build_portfolio_context(
                ticker=ticker,
                sector=sector_map[ticker],
                signal_data={"status": "validated"},
                human_quality=hq,
                opportunity=opp,
            )
            clf = classify_candidate(
                ticker=ticker,
                exposure_profile=pc["exposure_profile"],
                signal_data={"status": "validated"},
                hq_score=hq.get("score"),
                opp_status=opp.get("status"),
            )
            candidates.append({
                "ticker":           ticker,
                "name":             name_map[ticker],
                "sector":           sector_map[ticker],
                "type":             clf["type"],
                "reason":           clf["reason"],
                "role":             pc["role"],
                "risk_bucket":      pc["risk_bucket"],
                "conviction_level": pc["conviction"]["level"],
                "themes":           pc["themes"],
            })

        return JSONResponse(build_strategic_view(candidates))
    finally:
        db.close()


# ── Rotation log ──────────────────────────────────────────────────────────────

@app.get("/api/changes")
async def changes_endpoint(direction: str = Query("long"), limit: int = Query(100)):
    if direction not in {"long", "midterm", "opportunity"}:
        direction = "long"
    db = _open_db()
    try:
        # Tables may not exist yet — return empty gracefully
        tables = {r[0] for r in db.execute("SHOW TABLES").fetchall()}
        if "top10_changes" not in tables or "top10_snapshots" not in tables:
            return JSONResponse({"direction": direction, "changes": [], "snapshots": []})

        changes = db.execute("""
            SELECT ticker, change_type, old_rank, new_rank, snapshot_date
            FROM top10_changes
            WHERE direction = ?
            ORDER BY snapshot_date DESC, changed_at DESC
            LIMIT ?
        """, [direction, limit]).fetchall()

        last_date = db.execute(
            "SELECT MAX(snapshot_date) FROM top10_snapshots WHERE direction = ?",
            [direction],
        ).fetchone()[0]
        snapshots = []
        if last_date:
            snapshots = db.execute("""
                SELECT rank, ticker, avg_alpha, last_signal, n_signals
                FROM top10_snapshots WHERE direction = ? AND snapshot_date = ?
                ORDER BY rank
            """, [direction, last_date]).fetchall()

        return JSONResponse({
            "direction": direction,
            "changes": [
                {"ticker": r[0], "change_type": r[1], "old_rank": r[2],
                 "new_rank": r[3], "snapshot_date": str(r[4])[:10]}
                for r in changes
            ],
            "snapshots": [
                {"rank": r[0], "ticker": r[1], "avg_alpha": round(float(r[2]), 4) if r[2] else None,
                 "last_signal": str(r[3])[:10] if r[3] else None, "n_signals": r[4]}
                for r in snapshots
            ],
        })
    finally:
        db.close()


if __name__ == "__main__":
    uvicorn.run("signalalpha.wiki.app:app", host="127.0.0.1", port=8000, reload=True)
