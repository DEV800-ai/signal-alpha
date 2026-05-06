"""Auto-generator: scaffold signal wiki pages and keep AUTOGEN sections in sync.

Usage:
    uv run python -m signalalpha.wiki.autogen          # scaffold + refresh all
    uv run python -m signalalpha.wiki.autogen --dry-run
"""
from __future__ import annotations

import re
import subprocess
from collections import defaultdict
from datetime import date
from pathlib import Path

import duckdb

from signalalpha.config import DB_PATH

WIKI_ROOT = Path(__file__).resolve().parents[3] / "wiki"

_SIGNAL_NAME_CLEAN = re.compile(r"\[.*?\]")
_SAFE_ID = re.compile(r"[^\w.\-]")

# ── Helpers ───────────────────────────────────────────────────────────────────

def _clean_signal_id(name: str) -> str:
    clean = _SIGNAL_NAME_CLEAN.sub("", name).strip()
    clean = _SAFE_ID.sub("_", clean).strip("_")
    return clean or "unknown"


def _git_short_hash() -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=WIKI_ROOT.parent,
        )
        return r.stdout.strip() if r.returncode == 0 else "0000000"
    except Exception:
        return "0000000"


def _signal_status(row: dict) -> str:
    n = row.get("n_events") or 0
    p = row.get("p_value_vs_sector")
    if n < 30 or p is None:
        return "graveyard"
    if p < 0.05:
        return "validated"
    if p < 0.10:
        return "borderline"
    return "graveyard"


def _confidence(status: str) -> str:
    return {"validated": "medium", "borderline": "medium"}.get(status, "low")


def _infer_data_sources(signal_name: str) -> list[str]:
    name = signal_name.lower()
    if "earnings" in name:
        return ["db:earnings_events", "db:prices"]
    if "8k" in name or "filing" in name:
        return ["db:sec_filings", "db:prices"]
    return ["db:prices"]


def _fmt_pct(v: float | None, decimals: int = 2) -> str:
    if v is None:
        return "N/A"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v * 100:.{decimals}f}%"


def _fmt_float(v: float | None, decimals: int = 4) -> str:
    return "N/A" if v is None else f"{v:.{decimals}f}"


# ── Validation summary renderer ───────────────────────────────────────────────

def render_validation_summary(runs: list[dict]) -> str:
    """Render the AUTOGEN:BEGIN…END content for validation_summary."""
    lines: list[str] = ["<!-- claim_type: signal_summary -->", ""]

    for row in runs:
        run_date = str(row["run_at"])[:10]
        lines.append(f"[Run #{row['run_id']}](signal_run:{row['run_id']}) — {run_date}")
        lines.append("")

        n = row.get("n_events")
        ws = row.get("event_window_start")
        we = row.get("event_window_end")
        window = f" (window {ws} → {we})" if ws and we else ""
        if n is not None:
            lines.append(f"- N events: **{n}**{window}")

        hr = row.get("hit_rate")
        if hr is not None:
            lines.append(f"- Hit rate: **{hr*100:.1f}%**")

        mr = row.get("mean_return")
        hd = row.get("hold_days", "?")
        if mr is not None:
            lines.append(f"- Mean return: **{_fmt_pct(mr)}** over {hd} trading days")

        ma = row.get("mean_alpha_sector")
        if ma is not None:
            lines.append(f"- Mean alpha vs sector: **{_fmt_pct(ma)}**")

        p = row.get("p_value_vs_sector")
        if p is not None:
            if p < 0.05:
                verdict = f"below the 0.05 bar — **VALIDATED**"
            else:
                verdict = f"above the 0.05 bar — **NOT VALIDATED**"
            lines.append(f"- p-value vs sector: **{p:.4f}** — {verdict}")

        sh = row.get("sharpe_ann")
        if sh is not None:
            lines.append(f"- Sharpe (annualized): **{sh:.2f}**")

        md = row.get("max_drawdown")
        if md is not None:
            lines.append(f"- Max drawdown of sequential equity curve: **{md*100:.1f}%**")

        lines.append("")

    # Remove trailing blank line
    while lines and not lines[-1]:
        lines.pop()

    return "\n".join(lines)


# ── AUTOGEN section updater ───────────────────────────────────────────────────

def update_autogen_section(page_path: Path, section_name: str, new_content: str) -> bool:
    """Replace content between AUTOGEN markers. Returns True if the file changed."""
    text = page_path.read_text(encoding="utf-8")
    begin = f"<!-- AUTOGEN:BEGIN {section_name} -->"
    end = f"<!-- AUTOGEN:END {section_name} -->"

    bi = text.find(begin)
    ei = text.find(end)
    if bi == -1 or ei == -1:
        raise ValueError(f"AUTOGEN markers for '{section_name}' not found in {page_path}")

    new_text = (
        text[: bi + len(begin)]
        + "\n"
        + new_content
        + "\n"
        + text[ei:]
    )
    if new_text == text:
        return False
    page_path.write_text(new_text, encoding="utf-8")
    return True


# ── Page scaffolder ───────────────────────────────────────────────────────────

def scaffold_signal_page(
    signal_id: str,
    primary_run: dict,
    all_runs: list[dict],
    page_path: Path,
    code_version: str,
    today: date,
) -> None:
    """Write a fresh stub signal page with AUTOGEN markers filled."""
    status = _signal_status(primary_run)
    confidence = _confidence(status)
    data_sources = _infer_data_sources(primary_run["signal_name"])
    data_sources_yaml = "\n".join(f"  - {ds}" for ds in data_sources)
    event_max = str(primary_run.get("event_window_end") or today)
    run_date = str(primary_run["run_at"])[:10]
    hold_days = primary_run.get("hold_days", 30)
    validated_run_id = primary_run["run_id"]

    autogen_content = render_validation_summary(all_runs)

    # Decision history entries from all runs
    history_lines = []
    for r in sorted(all_runs, key=lambda x: x["run_id"]):
        rd = str(r["run_at"])[:10]
        st = _signal_status(r)
        history_lines.append(
            f"- {rd} — run_id={r['run_id']} completed. "
            f"[Results](signal_run:{r['run_id']}). Status: {st}."
        )

    history = "\n".join(history_lines) if history_lines else f"- {today} — page scaffolded."

    title = signal_id.replace("_", " ").replace(".", " ").title()

    content = f"""\
---
signal_id: {signal_id}
status: {status}
hold_days: {hold_days}
data_sources:
{data_sources_yaml}
validated_run_id: {validated_run_id}
code_version: {code_version}
event_max_date: {event_max}
lifecycle: draft
last_updated: {today}
last_reviewed: {today}
freshness_status: current
confidence: {confidence}
schema_version: 1
---

# {title}

## Definition

<!-- claim_type: factual_claim -->

_TODO: Describe the signal definition — what event fires, on what data, with what parameters._

## Validation summary

<!-- AUTOGEN:BEGIN validation_summary -->
{autogen_content}
<!-- AUTOGEN:END validation_summary -->

## Why it might work

<!-- claim_type: interpretation -->

_TODO: Describe the economic intuition behind why this signal should have predictive power._

## Known limitations

<!-- claim_type: risk_note -->

- _TODO: List known limitations, data gaps, or conditions where signal is unreliable._

## Comparable signals

<!-- claim_type: factual_claim -->

- _TODO: Link to related signals in the wiki._

## When to use / when NOT to use

<!-- claim_type: interpretation -->

- **USE when:** _TODO_
- **DO NOT use when:** _TODO_

## Decision history

<!-- claim_type: factual_claim -->

{history}
"""
    page_path.write_text(content, encoding="utf-8")


# ── Company signal history renderer ──────────────────────────────────────────

def render_signal_history(ticker: str, db: duckdb.DuckDBPyConnection) -> str:
    """Render the AUTOGEN:BEGIN…END content for signal_history on a company page."""
    try:
        rows = db.execute("""
            SELECT se.event_date, sr.signal_name, se.run_id,
                   se.net_return, se.alpha_sector, se.entry_date, se.exit_date
            FROM signal_events se
            JOIN signal_runs sr ON sr.run_id = se.run_id
            WHERE se.ticker = ?
            ORDER BY se.event_date DESC
            LIMIT 20
        """, [ticker]).fetchall()
    except Exception:
        rows = []

    lines = ["<!-- claim_type: signal_summary -->", ""]
    if not rows:
        lines.append("_No signal firings recorded for this ticker._")
        return "\n".join(lines)

    lines.append("| Date | Signal | Return | Alpha vs Sector | Source |")
    lines.append("|------|--------|--------|-----------------|--------|")
    for event_date, signal_name, run_id, net_return, alpha_sector, entry_date, exit_date in rows:
        date_str = str(event_date)[:10]
        ret = f"{net_return*100:+.1f}%" if net_return is not None else "—"
        alpha = f"{alpha_sector*100:+.1f}%" if alpha_sector is not None else "—"
        sid = _clean_signal_id(signal_name)
        lines.append(f"| {date_str} | [{sid}](../signals/{sid}.md) | {ret} | {alpha} | [run #{run_id}](signal_run:{run_id}) |")

    return "\n".join(lines)


def scaffold_company_page(
    ticker: str,
    name: str,
    sector: str,
    listing: str,
    notes: str,
    page_path: Path,
    today: date,
    db: duckdb.DuckDBPyConnection,
) -> None:
    """Write a fresh stub company page."""
    signal_history_content = render_signal_history(ticker, db)

    content = f"""\
---
ticker: {ticker}
slug: {ticker.lower()}
name: {name}
status: public
sector: {sector}
listing: {listing}
lifecycle: draft
last_updated: {today}
last_reviewed: {today}
freshness_status: current
confidence: low
schema_version: 1
---

# {name} ({ticker})

## Strategic position

<!-- claim_type: interpretation -->

_{notes or 'TODO: Describe the company strategic position in ≤80 words.'}_

## Bull case

<!-- claim_type: interpretation -->

- _TODO: One-sentence claim + source citation._
- _TODO: One-sentence claim + source citation._
- _TODO: One-sentence claim + source citation._

## Bear case

<!-- claim_type: interpretation -->

- _TODO: One-sentence claim + source citation._
- _TODO: One-sentence claim + source citation._
- _TODO: One-sentence claim + source citation._

## Priced in

<!-- claim_type: interpretation -->

_TODO: What is the market already pricing in? What would need to be true for the stock to outperform from here?_

## Recent catalysts

<!-- claim_type: factual_claim -->

| Date | Event | Source | Horizon | Outcome |
|------|-------|--------|---------|---------|
| _TODO_ | | | | |

## Signal history

<!-- AUTOGEN:BEGIN signal_history -->
{signal_history_content}
<!-- AUTOGEN:END signal_history -->

## Watch list

<!-- claim_type: risk_note -->

- _TODO: Concrete things to watch with measurable triggers._
"""
    page_path.write_text(content, encoding="utf-8")


# ── Main entry point ──────────────────────────────────────────────────────────

_BENCHMARK_SECTORS = frozenset(["benchmark"])


def run_autogen(
    wiki_root: Path | None = None,
    db: duckdb.DuckDBPyConnection | None = None,
    dry_run: bool = False,
) -> list[str]:
    """
    Scaffold missing signal + company pages and refresh all AUTOGEN sections.
    Returns list of file paths that were created or updated.
    """
    if wiki_root is None:
        wiki_root = WIKI_ROOT
    signals_dir = wiki_root / "signals"
    companies_dir = wiki_root / "companies" / "public"
    signals_dir.mkdir(parents=True, exist_ok=True)
    companies_dir.mkdir(parents=True, exist_ok=True)

    close_db = False
    if db is None:
        db = duckdb.connect(str(DB_PATH), read_only=True)
        close_db = True

    try:
        today = date.today()
        code_version = _git_short_hash()
        changed: list[str] = []

        # ── Signal pages ──────────────────────────────────────────────────────
        rows = db.execute("SELECT * FROM signal_runs ORDER BY run_id").fetchall()
        cols = [d[0] for d in db.execute("DESCRIBE signal_runs").fetchall()]
        run_dicts = [dict(zip(cols, r)) for r in rows]

        by_signal: dict[str, list[dict]] = defaultdict(list)
        for r in run_dicts:
            sid = _clean_signal_id(r["signal_name"])
            by_signal[sid].append(r)

        for signal_id, runs in sorted(by_signal.items()):
            page_path = signals_dir / f"{signal_id}.md"
            primary = min(runs, key=lambda r: r.get("p_value_vs_sector") or 1.0)

            if not page_path.exists():
                if not dry_run:
                    scaffold_signal_page(signal_id, primary, runs, page_path, code_version, today)
                changed.append(f"CREATED {page_path}")
            else:
                new_content = render_validation_summary(runs)
                if not dry_run:
                    try:
                        updated = update_autogen_section(page_path, "validation_summary", new_content)
                        if updated:
                            changed.append(f"UPDATED {page_path}")
                    except ValueError as e:
                        changed.append(f"SKIP {page_path}: {e}")
                else:
                    changed.append(f"WOULD UPDATE {page_path}")

        # ── Company pages ─────────────────────────────────────────────────────
        universe = db.execute(
            "SELECT ticker, name, sector, notes FROM universe ORDER BY ticker"
        ).fetchall()

        for ticker, name, sector, notes in universe:
            if sector in _BENCHMARK_SECTORS:
                continue
            page_path = companies_dir / f"{ticker}.md"

            if not page_path.exists():
                if not dry_run:
                    scaffold_company_page(
                        ticker, name or ticker, sector, "NASDAQ",
                        notes or "", page_path, today, db,
                    )
                changed.append(f"CREATED {page_path}")
            else:
                # Refresh AUTOGEN signal_history section
                new_content = render_signal_history(ticker, db)
                if not dry_run:
                    try:
                        updated = update_autogen_section(page_path, "signal_history", new_content)
                        if updated:
                            changed.append(f"UPDATED {page_path}")
                    except ValueError as e:
                        changed.append(f"SKIP {page_path}: {e}")
                else:
                    changed.append(f"WOULD UPDATE {page_path}")

    finally:
        if close_db:
            db.close()

    return changed


if __name__ == "__main__":
    import sys
    dry = "--dry-run" in sys.argv
    results = run_autogen(dry_run=dry)
    for line in results:
        print(line)
    print(f"\n{'Dry run — ' if dry else ''}Done: {len(results)} page(s) affected.")
