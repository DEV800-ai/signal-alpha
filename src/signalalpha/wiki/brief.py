"""Daily Signal Brief — aggregate signal state with wiki context."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import duckdb
import yaml

from signalalpha.wiki.autogen import WIKI_ROOT, _clean_signal_id, _signal_status

_STALE_DAYS = 30


def _read_frontmatter(page_path: Path) -> dict:
    try:
        text = page_path.read_text(encoding="utf-8")
        if not text.startswith("---"):
            return {}
        parts = text.split("---", 2)
        if len(parts) < 3:
            return {}
        return yaml.safe_load(parts[1]) or {}
    except Exception:
        return {}


def _context_status(page_path: Path | None, today: date) -> str:
    if page_path is None or not page_path.exists():
        return "missing"
    fm = _read_frontmatter(page_path)
    fs = fm.get("freshness_status", "")
    if fs == "stale":
        return "stale"
    last_updated = fm.get("last_updated")
    if last_updated:
        try:
            lu = date.fromisoformat(str(last_updated))
            if (today - lu).days > _STALE_DAYS:
                return "stale"
        except ValueError:
            pass
    if fs == "current":
        return "current"
    return "stale"


def build_daily_brief(db: duckdb.DuckDBPyConnection) -> dict:
    """
    Return the current signal research state:
    best run per signal, joined with wiki context.
    """
    today = date.today()
    signals_dir = WIKI_ROOT / "signals"

    rows = db.execute("""
        SELECT
            run_id, signal_name, hold_days, n_events,
            event_window_start, event_window_end,
            hit_rate, mean_return, mean_alpha_sector,
            p_value_vs_sector, sharpe_ann, max_drawdown,
            params_json, run_at
        FROM signal_runs
        ORDER BY p_value_vs_sector ASC NULLS LAST, run_id DESC
    """).fetchall()

    cols = [
        "run_id", "signal_name", "hold_days", "n_events",
        "event_window_start", "event_window_end",
        "hit_rate", "mean_return", "mean_alpha_sector",
        "p_value_vs_sector", "sharpe_ann", "max_drawdown",
        "params_json", "run_at",
    ]

    # Best run per signal (lowest p_value already first)
    seen: set[str] = set()
    entries = []

    for r in rows:
        d = dict(zip(cols, r))
        signal_id = _clean_signal_id(d["signal_name"])
        if signal_id in seen:
            continue
        seen.add(signal_id)

        status = _signal_status(d)
        page_path = signals_dir / f"{signal_id}.md"
        ctx = _context_status(page_path if page_path.exists() else None, today)
        fm = _read_frontmatter(page_path) if page_path.exists() else {}

        entries.append({
            "signal_id": signal_id,
            "signal_name": d["signal_name"],
            "run_id": d["run_id"],
            "status": status,
            "hold_days": d["hold_days"],
            "n_events": d["n_events"],
            "event_window_start": str(d["event_window_start"])[:10] if d["event_window_start"] else None,
            "event_window_end": str(d["event_window_end"])[:10] if d["event_window_end"] else None,
            "hit_rate": round(float(d["hit_rate"]), 6) if d["hit_rate"] is not None else None,
            "mean_return": round(float(d["mean_return"]), 6) if d["mean_return"] is not None else None,
            "mean_alpha_sector": round(float(d["mean_alpha_sector"]), 6) if d["mean_alpha_sector"] is not None else None,
            "p_value_vs_sector": round(float(d["p_value_vs_sector"]), 6) if d["p_value_vs_sector"] is not None else None,
            "sharpe_ann": round(float(d["sharpe_ann"]), 4) if d["sharpe_ann"] is not None else None,
            "context_status": ctx,
            "wiki_path": str(page_path.relative_to(WIKI_ROOT.parent)) if page_path.exists() else None,
            "lifecycle": fm.get("lifecycle"),
            "last_updated": str(fm.get("last_updated", "")) or None,
            "run_at": str(d["run_at"])[:10] if d["run_at"] else None,
        })

    return {"generated_at": str(today), "signals": entries}
