"""DuckDB connection and schema management."""
from __future__ import annotations

import duckdb

from signalalpha.config import DB_PATH, DATA_DIR

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS universe (
    sector       VARCHAR NOT NULL,
    ticker       VARCHAR NOT NULL PRIMARY KEY,
    name         VARCHAR,
    active_from  DATE,
    active_to    DATE,
    notes        VARCHAR
);

CREATE TABLE IF NOT EXISTS prices (
    ticker  VARCHAR NOT NULL,
    date    DATE    NOT NULL,
    open    DOUBLE,
    high    DOUBLE,
    low     DOUBLE,
    close   DOUBLE,
    volume  BIGINT,
    PRIMARY KEY (ticker, date)
);

CREATE INDEX IF NOT EXISTS prices_date_idx ON prices(date);

CREATE TABLE IF NOT EXISTS ingestion_log (
    source        VARCHAR NOT NULL,
    ticker        VARCHAR NOT NULL,
    last_date     DATE,
    fetched_at    TIMESTAMP DEFAULT now(),
    rows_inserted INTEGER,
    PRIMARY KEY (source, ticker)
);

CREATE TABLE IF NOT EXISTS sec_filings (
    accession    VARCHAR NOT NULL PRIMARY KEY,
    cik          VARCHAR NOT NULL,
    ticker       VARCHAR NOT NULL,
    form         VARCHAR NOT NULL,
    filing_date  DATE    NOT NULL,
    report_date  DATE,
    primary_doc  VARCHAR,
    items        VARCHAR              -- 8-K item codes if applicable
);
CREATE INDEX IF NOT EXISTS sec_filings_ticker_date_idx ON sec_filings(ticker, filing_date);
CREATE INDEX IF NOT EXISTS sec_filings_form_idx ON sec_filings(form);

CREATE TABLE IF NOT EXISTS sec_form4 (
    accession        VARCHAR NOT NULL,
    ticker           VARCHAR NOT NULL,
    cik              VARCHAR NOT NULL,
    filing_date      DATE NOT NULL,
    transaction_date DATE,
    transaction_code VARCHAR,            -- 'P' open-market purchase, 'S' sale, etc.
    insider_name     VARCHAR,
    insider_title    VARCHAR,
    shares           DOUBLE,
    price_per_share  DOUBLE,
    transaction_usd  DOUBLE,
    PRIMARY KEY (accession, transaction_date, transaction_code, insider_name, shares)
);
CREATE INDEX IF NOT EXISTS sec_form4_ticker_date_idx ON sec_form4(ticker, filing_date);

CREATE TABLE IF NOT EXISTS earnings_events (
    ticker          VARCHAR NOT NULL,
    event_date      TIMESTAMP NOT NULL,    -- announcement timestamp from yfinance
    event_date_adj  DATE NOT NULL,         -- BMO/AMC-adjusted for backtest entry
    session         VARCHAR NOT NULL,      -- 'bmo' or 'amc'
    eps_estimate    DOUBLE,
    eps_actual      DOUBLE,
    surprise_pct    DOUBLE,
    PRIMARY KEY (ticker, event_date)
);

CREATE TABLE IF NOT EXISTS sources (
    source_uri    VARCHAR NOT NULL PRIMARY KEY,  -- e.g. web:https://..., news:..., transcript:...
    scheme        VARCHAR NOT NULL,
    title         VARCHAR,
    published_at  TIMESTAMP,
    fetched_at    TIMESTAMP DEFAULT now(),
    summary       VARCHAR
);
CREATE INDEX IF NOT EXISTS sources_scheme_idx ON sources(scheme);
CREATE INDEX IF NOT EXISTS sources_published_idx ON sources(published_at);

CREATE SEQUENCE IF NOT EXISTS signal_event_seq START 1;

CREATE TABLE IF NOT EXISTS signal_events (
    id               INTEGER PRIMARY KEY DEFAULT nextval('signal_event_seq'),
    run_id           INTEGER NOT NULL,
    ticker           VARCHAR NOT NULL,
    event_date       DATE    NOT NULL,
    entry_date       DATE,
    exit_date        DATE,
    entry_px         DOUBLE,
    exit_px          DOUBLE,
    gross_return     DOUBLE,
    net_return       DOUBLE,
    sector_benchmark VARCHAR,
    sector_return    DOUBLE,
    spy_return       DOUBLE,
    alpha_sector     DOUBLE,
    alpha_spy        DOUBLE
);
CREATE INDEX IF NOT EXISTS signal_events_run_idx    ON signal_events(run_id);
CREATE INDEX IF NOT EXISTS signal_events_ticker_idx ON signal_events(ticker);

CREATE SEQUENCE IF NOT EXISTS signal_run_seq START 1;

CREATE TABLE IF NOT EXISTS signal_runs (
    run_id              INTEGER PRIMARY KEY DEFAULT nextval('signal_run_seq'),
    signal_name         VARCHAR NOT NULL,
    run_at              TIMESTAMP DEFAULT now(),
    hold_days           INTEGER NOT NULL,
    event_window_start  DATE,
    event_window_end    DATE,
    n_events            INTEGER,
    n_dropped           INTEGER,
    hit_rate            DOUBLE,
    mean_return         DOUBLE,
    median_return       DOUBLE,
    std_return          DOUBLE,
    sharpe_ann          DOUBLE,
    max_drawdown        DOUBLE,
    mean_alpha_sector   DOUBLE,
    mean_alpha_spy      DOUBLE,
    hit_rate_vs_sector  DOUBLE,
    p_value_vs_zero     DOUBLE,
    p_value_vs_sector   DOUBLE,
    params_json         VARCHAR,
    notes               VARCHAR
);
"""


def connect(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH), read_only=read_only)
    if not read_only:
        con.execute(SCHEMA_SQL)
    return con
