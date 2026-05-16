"""Admin endpoints and rotation-snapshot helpers."""
from __future__ import annotations

import os
import traceback
from datetime import date, datetime

import duckdb
from fastapi import APIRouter, BackgroundTasks, Header, UploadFile
from fastapi.responses import JSONResponse

from signalalpha.config import DB_PATH
from signalalpha.wiki.autogen import run_autogen

router = APIRouter()


# ── DB helper (shared with app.py via import) ─────────────────────────────────

def _open_db(read_only: bool = True) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(DB_PATH), read_only=read_only)


# ── Auth ──────────────────────────────────────────────────────────────────────

def _check_admin(authorization: str | None) -> bool:
    """Return True if the Authorization header carries the correct Bearer token."""
    expected = os.environ.get("ADMIN_SECRET", "")
    if not expected or not authorization:
        return False
    parts = authorization.split(" ", 1)
    return len(parts) == 2 and parts[0].lower() == "bearer" and parts[1] == expected


# ── Rotation tables ───────────────────────────────────────────────────────────

def _init_rotation_tables(db: duckdb.DuckDBPyConnection) -> None:
    db.execute("""
        CREATE TABLE IF NOT EXISTS top10_snapshots (
            snapshot_date DATE,
            direction     TEXT,
            rank          INTEGER,
            ticker        TEXT,
            score         DOUBLE,
            last_signal   DATE,
            n_signals     INTEGER,
            avg_alpha     DOUBLE
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS top10_changes (
            changed_at    TIMESTAMP,
            direction     TEXT,
            ticker        TEXT,
            change_type   TEXT,
            old_rank      INTEGER,
            new_rank      INTEGER,
            snapshot_date DATE
        )
    """)


def _snapshot_top10() -> None:
    """Snapshot current top10 (long/midterm/opportunity) and record entry/exit/rank changes."""
    today = date.today()

    db = _open_db(read_only=False)
    try:
        _init_rotation_tables(db)

        for direction in ("long", "midterm", "opportunity"):
            last_date = db.execute(
                "SELECT MAX(snapshot_date) FROM top10_snapshots WHERE direction = ?",
                [direction],
            ).fetchone()[0]
            if last_date and str(last_date)[:10] == str(today):
                continue

            if direction == "long":
                dir_having = ""
                score_col = (
                    "AVG(se.alpha_sector)"
                    " * (SUM(CASE WHEN se.net_return > 0 THEN 1.0 ELSE 0.0 END) / NULLIF(COUNT(*), 0))"
                    " * LN(COUNT(*) + 1)"
                )
                extra_join = ""
                extra_group = ""
            elif direction == "opportunity":
                dir_having = "AND AVG(se.alpha_sector) > 0 AND STDDEV(se.net_return) > 0"
                score_col = """CASE WHEN sma.sma50 IS NOT NULL AND sma.current_price < sma.sma50
                    THEN (AVG(se.alpha_sector) * (SUM(CASE WHEN se.net_return > 0 THEN 1.0 ELSE 0.0 END) / NULLIF(COUNT(*), 0)) * LN(COUNT(*) + 1))
                         * (1 + GREATEST(0, (sma.sma50 - sma.current_price) / NULLIF(sma.sma50, 0)) * 3)
                    ELSE (AVG(se.alpha_sector) * (SUM(CASE WHEN se.net_return > 0 THEN 1.0 ELSE 0.0 END) / NULLIF(COUNT(*), 0)) * LN(COUNT(*) + 1))
                    END"""
                extra_join = (
                    "LEFT JOIN (SELECT ticker,"
                    " LAST(close ORDER BY date) AS current_price,"
                    " AVG(close) FILTER (WHERE date >= CURRENT_DATE - INTERVAL '50 days') AS sma50"
                    " FROM prices GROUP BY ticker) sma ON sma.ticker = se.ticker"
                )
                extra_group = ", sma.current_price, sma.sma50"
            else:  # midterm
                dir_having = "AND AVG(se.alpha_sector) > 0 AND STDDEV(se.net_return) > 0"
                score_col = (
                    "CASE WHEN STDDEV(se.net_return) > 0"
                    " THEN (AVG(se.alpha_sector) / STDDEV(se.net_return))"
                    "       * (SUM(CASE WHEN se.net_return > 0 THEN 1.0 ELSE 0.0 END) / NULLIF(COUNT(*), 0))"
                    "       * LN(COUNT(*) + 1)"
                    " ELSE 0 END"
                )
                extra_join = ""
                extra_group = ""

            rows = db.execute(f"""
                SELECT se.ticker, MAX(se.event_date) AS last_signal,
                       COUNT(*) AS n_signals, AVG(se.alpha_sector) AS avg_alpha,
                       {score_col} AS score
                FROM signal_events se
                JOIN signal_runs sr ON sr.run_id = se.run_id
                JOIN universe    u  ON u.ticker  = se.ticker
                {extra_join}
                JOIN (SELECT signal_name, MAX(run_id) AS latest_run_id
                      FROM signal_runs GROUP BY signal_name) lr
                  ON lr.signal_name = sr.signal_name AND lr.latest_run_id = sr.run_id
                WHERE sr.p_value_vs_sector < 0.05
                GROUP BY se.ticker {extra_group}
                HAVING COUNT(*) >= 5 {dir_having}
                  AND MAX(se.event_date) >= CURRENT_DATE - INTERVAL '90 days'
                ORDER BY score DESC NULLS LAST
                LIMIT 10
            """).fetchall()

            current_map = {r[0]: i + 1 for i, r in enumerate(rows)}

            prev_rows = (
                db.execute(
                    "SELECT ticker, rank FROM top10_snapshots"
                    " WHERE direction = ? AND snapshot_date = ? ORDER BY rank",
                    [direction, last_date],
                ).fetchall()
                if last_date else []
            )
            prev_map = {r[0]: r[1] for r in prev_rows}

            for ticker in set(prev_map) | set(current_map):
                old_rank = prev_map.get(ticker)
                new_rank = current_map.get(ticker)
                if old_rank == new_rank:
                    continue
                if old_rank is None:
                    change_type = "entered"
                elif new_rank is None:
                    change_type = "exited"
                elif new_rank < old_rank:
                    change_type = "moved_up"
                else:
                    change_type = "moved_down"
                db.execute(
                    "INSERT INTO top10_changes VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [datetime.now(), direction, ticker, change_type, old_rank, new_rank, today],
                )

            for rank, r in enumerate(rows, 1):
                db.execute(
                    "INSERT INTO top10_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    [today, direction, rank, r[0], r[4], r[1], r[2], r[3]],
                )
    finally:
        db.close()


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/admin/snapshot")
async def snapshot_endpoint(authorization: str | None = Header(default=None)):
    """Manually trigger a top10 snapshot. Requires Authorization: Bearer <secret>."""
    if not _check_admin(authorization):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        _snapshot_top10()
        db = _open_db()
        try:
            counts = {
                d: db.execute(
                    "SELECT COUNT(*) FROM top10_snapshots WHERE direction = ?", [d]
                ).fetchone()[0]
                for d in ("long", "midterm", "opportunity")
            }
        finally:
            db.close()
        return JSONResponse({"ok": True, "snapshot_counts": counts})
    except Exception as e:
        return JSONResponse(
            {"ok": False, "error": str(e), "traceback": traceback.format_exc()},
            status_code=500,
        )


@router.post("/admin/ingest")
async def ingest_endpoint(
    background_tasks: BackgroundTasks,
    authorization: str | None = Header(default=None),
):
    """Trigger incremental price ingestion. Requires Authorization: Bearer <secret>."""
    if not _check_admin(authorization):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    def _run():
        import traceback as _tb
        from signalalpha.ingest_prices import ingest_all
        from signalalpha.ingest_fundamentals import ingest_all as ingest_fundamentals
        from signalalpha.live_signals import run_live_signals
        try:
            ingest_all()
        except Exception:
            print("ERROR in ingest_all:\n" + _tb.format_exc(), flush=True)
        try:
            ingest_fundamentals()
        except Exception:
            print("ERROR in ingest_fundamentals:\n" + _tb.format_exc(), flush=True)
        try:
            run_live_signals()
        except Exception:
            print("ERROR in run_live_signals:\n" + _tb.format_exc(), flush=True)
        try:
            _snapshot_top10()
        except Exception:
            print("ERROR in _snapshot_top10:\n" + _tb.format_exc(), flush=True)

    background_tasks.add_task(_run)
    return JSONResponse({"ok": True, "status": "ingestion + signal re-run started in background"})


@router.post("/admin/restore-db")
async def restore_db(
    file: UploadFile,
    authorization: str | None = Header(default=None),
):
    """Upload a DuckDB snapshot to the volume. Requires Authorization: Bearer <secret>."""
    if not _check_admin(authorization):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    data = await file.read()
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    DB_PATH.write_bytes(data)
    return JSONResponse({"ok": True, "bytes": len(data), "path": str(DB_PATH)})


@router.get("/admin/health")
async def health_endpoint(authorization: str | None = Header(default=None)):
    """Return last price date and signal run date. Requires Authorization: Bearer <secret>."""
    if not _check_admin(authorization):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    db = _open_db()
    try:
        last_price = db.execute("SELECT MAX(date) FROM prices").fetchone()[0]
        last_signal = db.execute("SELECT MAX(run_at) FROM signal_runs").fetchone()[0]
        last_snapshot = db.execute("SELECT MAX(snapshot_date) FROM top10_snapshots").fetchone()[0]
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
    finally:
        db.close()
    return JSONResponse({
        "ok": True,
        "last_price_date": str(last_price) if last_price else None,
        "last_signal_run": str(last_signal) if last_signal else None,
        "last_snapshot_date": str(last_snapshot) if last_snapshot else None,
    })


@router.post("/autogen")
async def autogen_endpoint():
    results = run_autogen()
    return JSONResponse({"results": results})
