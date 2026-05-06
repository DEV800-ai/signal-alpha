# Citation grammar

Defines the citation URI scheme used throughout the wiki. Every citation in a wiki page MUST be one of these forms. The Validator agent rejects any draft whose citations don't parse or resolve.

## Grammar (BNF)

```
citation_uri   ::= scheme ":" entity_id [ "#" fragment ]
scheme         ::= "filing" | "tx" | "earnings" | "signal_run"
                 | "price" | "news" | "transcript" | "patent" | "web"
entity_id      ::= one or more ASCII chars (printable, no whitespace, no "#")
fragment       ::= one or more ASCII chars (printable, no whitespace)
```

URIs are case-sensitive. No leading or trailing whitespace. No spaces inside.

### Per-scheme entity_id constraints

The base grammar above is permissive on purpose (so new schemes can fit). Each scheme then narrows `entity_id` further. The Validator parses these per-scheme regexes when resolving citations.

| Scheme | entity_id pattern | Notes |
| --- | --- | --- |
| `filing` | `^\d{10}-\d{2}-\d{6}$` | SEC accession number |
| `tx` | `^\d{10}-\d{2}-\d{6}:\d+$` | accession + transaction index |
| `earnings` | `^[A-Z]{1,5}:\d{4}-\d{2}-\d{2}$` | ticker + ISO date |
| `signal_run` | `^\d+$` | positive integer |
| `price` | `^[A-Z]{1,5}:\d{4}-\d{2}-\d{2}$` | ticker + ISO date |
| `news` | `^[a-z][a-z0-9_]*\/\d{4}-\d{2}-\d{2}\/[a-z0-9-]+$` | publisher / date / kebab-slug |
| `transcript` | `^[A-Z]{1,5}:\d{4}-Q[1-4]$` or `^[A-Z]{1,5}:\d{4}-\d{2}-\d{2}$` | ticker + period |
| `patent` | `^(US\|WO\|EP)-[A-Z0-9-]+$` | issuing-office prefix + body |
| `web` | full URL (`^https?://...`) | last-resort scheme |

**v1 enforcement:** Pass 3 resolves citations by table lookup (existence is the source of truth). The per-scheme regexes above are the **Researcher's drafting contract** — they catch malformed URIs before resolution. The Validator MAY enforce them as a syntax check; it MUST not silently strip or rewrite a URI that fails them.

These patterns are conservative. If a real-world counter-example appears (e.g., a six-character ticker after a corporate action), update the pattern in this doc and bump `schema_version`.

## Markdown form

Citations appear inside a markdown link with a human-readable label:

```markdown
The deal was announced via 8-K [Item 1.01 dated 2026-04-22](filing:0001127602-26-018000#item-1.01).
```

The label is for humans. The URI in the parentheses is the machine-checkable part.

## Citation vs. wiki cross-link vs. plain external link

Markdown links in the wiki fall into three categories. The Validator decides which based on the link target:

| Link target shape | Category | Validation |
| --- | --- | --- |
| `<scheme>:<entity_id>[#<fragment>]` where `<scheme>` is in this grammar | citation | Pass 3 — syntax + resolution against DuckDB / `sources` table |
| `<relative-path>.md[#<anchor>]` | wiki cross-link | Pass 5 — file existence (after path normalization) |
| `https://...` (no `web:` prefix) | plain external link | not validated; informational only |
| anything else | ambiguous | Pass 3 FAIL with diagnostic |

If you intend a URL to be a *citation*, use `web:https://...`. A bare `https://...` is treated as informational and is not entered into the `sources` table or checked.

## Schemes (current set)

### `filing:<accession>`

A single SEC filing. Accession number is the SEC-issued primary key.

- Resolves via: `SELECT * FROM sec_filings WHERE accession = ?`
- Stability: SEC accession numbers never change.
- Fragment: optional, names a subsection (e.g., `#item-1.01`, `#exhibit-99.1`). Validator does not currently parse fragments — they're a hint to the reader.

Examples:

```
filing:0001127602-26-018000
filing:0001193125-24-249123#item-2.02
```

### `tx:<accession>:<index>`

A single non-derivative transaction inside a Form 4 filing. `<index>` is the position of the transaction within the filing's `nonDerivativeTable`, starting at 0.

- Resolves via: `SELECT * FROM sec_form4 WHERE accession = ? ORDER BY transaction_date, transaction_code, insider_name, shares LIMIT 1 OFFSET ?`
- Stability: composite key is deterministic for a given filing's XML.
- Fragment: not used.

Examples:

```
tx:0001127602-26-018000:0
tx:0001193125-24-249123:2
```

### `earnings:<ticker>:<date>`

An earnings announcement. `<date>` is the ISO date of the announcement (the calendar day, not the BMO/AMC-adjusted entry date).

- Resolves via: `SELECT * FROM earnings_events WHERE ticker = ? AND date(event_date) = ?`
- Stability: the (ticker, calendar-date) pair is unique even when yfinance restates EPS values.
- Fragment: not used.

Examples:

```
earnings:INTC:2026-04-24
earnings:NVDA:2025-02-26
```

### `signal_run:<run_id>`

A row in `signal_runs` — i.e., a recorded backtest result.

- Resolves via: `SELECT * FROM signal_runs WHERE run_id = ?`
- Stability: `run_id` is monotonically increasing and never reused.
- Fragment: not used.

Examples:

```
signal_run:2
signal_run:17
```

### `price:<ticker>:<date>`

A single daily price bar. Used sparingly — most price citations are date ranges, which can be encoded as two `price:` URIs in the same sentence.

- Resolves via: `SELECT * FROM prices WHERE ticker = ? AND date = ?`
- Stability: prices are immutable in the local store; if yfinance restates, we keep both versions in `ingestion_log`.
- Fragment: not used.

Examples:

```
price:NVDA:2024-01-03
price:INTC:2025-08-04
```

### `news:<publisher>/<date>/<slug>`

A news article. Resolves through the `sources` table (external source).

- `<publisher>` is a short canonical name (`reuters`, `bloomberg`, `wsj`, `theinformation`, `axios`). Lowercase, no spaces.
- `<date>` is the publication ISO date.
- `<slug>` is a short kebab-case identifier — typically derived from the URL path or the headline.
- Resolves via: `SELECT * FROM sources WHERE source_uri = 'news:...'`
- Stability: requires `sources` row to exist; ideally with a `snapshot_path` for archival.
- Fragment: optional — names a section/paragraph in the article (`#paragraph-3`).

Examples:

```
news:reuters/2026-04-19/intel-arm-deal
news:bloomberg/2025-11-08/nvidia-blackwell-ramp#paragraph-2
```

### `transcript:<ticker>:<period>[#<fragment>]`

An earnings call transcript or investor day transcript.

- `<period>` is `<YYYY>-Q<n>` (`2026-Q1`) for quarterly calls, or a date for ad-hoc events.
- `#<fragment>` typically refers to a page or section (`#p4`, `#qna-jpm`).
- Resolves via: `SELECT * FROM sources WHERE source_uri = 'transcript:...'`
- Stability: requires `sources` row, ideally with `snapshot_path`.

Examples:

```
transcript:INTC:2026-Q1
transcript:NVDA:2025-Q4#p7
```

### `patent:<patent_id>`

A USPTO grant or publication. Patent IDs are SEC-style stable.

- `<patent_id>` follows USPTO conventions (`US-11234567-B2`, `WO-2023-123456-A1`).
- Resolves via: `SELECT * FROM sources WHERE source_uri = 'patent:...'`
- Stability: USPTO IDs never change.

Examples:

```
patent:US-11234567-B2
patent:US-2023-0123456-A1
```

### `web:<url>`

Last-resort scheme for URLs that don't fit a typed scheme. **Avoid when possible** — typed schemes give richer rendering.

- `<url>` is a full URL, including `https://`.
- Resolves via: `SELECT * FROM sources WHERE source_uri = 'web:<url>'`
- Stability: depends entirely on the URL's host. `snapshot_path` strongly recommended.
- The daily report displays `web:` citations with a small "untyped source" indicator to encourage migration to typed schemes.

Example:

```
web:https://research.foo.com/notes/intel-foundry-q3
```

## The `sources` table (used by external schemes)

```sql
CREATE TABLE sources (
    source_uri      VARCHAR PRIMARY KEY,    -- the citation URI itself
    scheme          VARCHAR NOT NULL,       -- "news" | "transcript" | "patent" | "web"
    title           VARCHAR,
    canonical_url   VARCHAR,
    publisher       VARCHAR,                -- "reuters" | "bloomberg" | "uspto" | etc.
    published_at    DATE,
    accessed_at     TIMESTAMP DEFAULT now(),
    snapshot_path   VARCHAR,                -- optional local archive
    notes           VARCHAR
);
```

Required fields: `source_uri`, `scheme`, `canonical_url`, `published_at` (or `accessed_at` if no publication date is known).

`snapshot_path` is optional but strongly preferred for `news:` and `web:` schemes, since URLs rot.

## Validator algorithm

```
for each citation in a draft:
    parse the URI:
        if syntax invalid → FAIL
    if scheme is one of {filing, tx, earnings, signal_run, price}:
        look up entity in the corresponding DuckDB table
        if not found → FAIL
    else if scheme is one of {news, transcript, patent, web}:
        look up entity in `sources` table by exact source_uri match
        if not found → FAIL
    else:
        unknown scheme → FAIL
return PASS if all citations resolve, else list of failures
```

The Validator does **not** currently:
- Verify URLs are reachable (out of scope — would slow drafts).
- Inspect snapshots for content match.
- Cross-check that the source supports the claim (curator's job).

## Stability rules

1. **Once a citation is published in a live wiki page, it must continue to resolve forever.**
2. DuckDB rows that have been cited must not be deleted. (Soft-delete with a `deleted_at` flag if needed; the Validator treats them as resolvable.)
3. New schemes can be added at any time. Existing schemes can never be renamed or removed.
4. The grammar above is versioned via `schema_version` in the wiki page frontmatter — old pages can stay on older versions; new schemes apply only to new content.
5. External sources cited with `news:`, `transcript:`, `patent:`, `web:` should have `snapshot_path` populated. Phase 3 will enforce this; Phase 2 only specifies it.

## Anti-patterns

- **Citing the wiki itself.** Citations point to *sources*, not to other wiki pages. Use a regular markdown link for cross-page references.
- **Citing a paraphrase.** Cite the source, not your own page that paraphrases the source.
- **`web:` everywhere.** If you find yourself reaching for `web:` repeatedly for one publisher, propose a typed scheme.
- **Citation laundering.** Don't cite a Bloomberg article that itself just summarizes an SEC filing — cite the filing.
- **Ranges as a single citation.** A claim about "Q1 2026 results" cites the Q1 8-K, not the entire quarter. If you need a range, write two citations.
- **Citing source code.** Don't wrap `src/...` paths in `web:<github-url>` to make them "citable." Name the file in prose; the page's `code_version` frontmatter field already pins the exact ref. The wiki is a narrative layer, not code blame.

## Examples (worked)

> The foundry agreement was announced via 8-K [Item 1.01](filing:0001127602-26-018000#item-1.01) on 2026-04-22 and the company's CEO commented on the call ([transcript Q1 2026 p.4](transcript:INTC:2026-Q1#p4)). Q1 EPS came in at [$0.32 vs $0.18 estimate](earnings:INTC:2026-04-24).

This sentence has three citations. All three can be checked by the Validator: two against DuckDB tables (`sec_filings`, `earnings_events`) and one against the `sources` table.

> The volume_anomaly signal has [validated alpha of +1.37% vs sector](signal_run:2) over a 30-day hold.

One citation, against `signal_runs`.

> CEO Pat Gelsinger sold ~30k shares ([transaction filed 2024-08-15](tx:0001127602-24-019432:0)).

One citation against `sec_form4`, with the transaction-index suffix.
