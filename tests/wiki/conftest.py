"""Shared fixtures for wiki validator tests."""
from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def db():
    """Minimal in-memory DuckDB seeded to resolve citations in volume_anomaly_pass.md."""
    con = duckdb.connect(":memory:")
    con.execute("""
        CREATE TABLE signal_runs (
            run_id INTEGER PRIMARY KEY,
            signal_name VARCHAR NOT NULL,
            hold_days INTEGER NOT NULL
        )
    """)
    con.execute("INSERT INTO signal_runs VALUES (2, 'volume_anomaly', 30)")

    con.execute("""
        CREATE TABLE sec_filings (
            accession VARCHAR PRIMARY KEY,
            cik VARCHAR,
            ticker VARCHAR,
            form VARCHAR,
            filing_date DATE,
            report_date DATE,
            primary_doc VARCHAR,
            items VARCHAR
        )
    """)
    con.execute("""
        CREATE TABLE sec_form4 (
            accession VARCHAR,
            ticker VARCHAR,
            cik VARCHAR,
            filing_date DATE,
            transaction_date DATE,
            transaction_code VARCHAR,
            insider_name VARCHAR,
            insider_title VARCHAR,
            shares DOUBLE,
            price_per_share DOUBLE,
            transaction_usd DOUBLE
        )
    """)
    con.execute("""
        CREATE TABLE earnings_events (
            ticker VARCHAR,
            event_date TIMESTAMP,
            event_date_adj DATE,
            session VARCHAR,
            eps_estimate DOUBLE,
            eps_actual DOUBLE,
            surprise_pct DOUBLE,
            PRIMARY KEY (ticker, event_date)
        )
    """)
    con.execute("""
        CREATE TABLE prices (
            ticker VARCHAR,
            date DATE,
            open DOUBLE,
            high DOUBLE,
            low DOUBLE,
            close DOUBLE,
            volume BIGINT,
            PRIMARY KEY (ticker, date)
        )
    """)
    con.execute("""
        CREATE TABLE sources (
            source_uri VARCHAR PRIMARY KEY,
            scheme VARCHAR NOT NULL,
            title VARCHAR,
            canonical_url VARCHAR,
            publisher VARCHAR,
            published_at DATE,
            accessed_at TIMESTAMP DEFAULT now(),
            snapshot_path VARCHAR,
            notes VARCHAR
        )
    """)

    yield con
    con.close()
