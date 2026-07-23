## Project Status

### Phase 1: SEC EDGAR Client & Schedule of Investments Parser — Complete

**Scope**: Parse BXSL's (Blackstone Secured Lending Fund) Condensed Consolidated Schedule of Investments from its 10-Q filing (period ended March 31, 2026) into a structured, analysis-ready dataset.

**What was built**:
- `src/edgar_client.py` — SEC EDGAR API client for fetching filing metadata and documents (handles SEC's required User-Agent header and rate limiting)
- `src/parser.py` — HTML table parser that reconstructs row-level investment data from a raw filing, handling:
  - Multi-level category hierarchy (debt type → industry) expressed as row structure rather than columns
  - Cosmetic formatting quirks (currency/percent symbols shown only once per block, empty spacer cells)
  - Multiple distinct row schemas: floating-rate debt, fixed-rate debt, common equity, preferred equity, unfunded commitments
  - Non-USD denominated positions (EUR, GBP, SEK, NOK, DKK, and other ISO 4217 currencies)
  - Section totals and page-break continuations ("(continued)" labels)

**Results**:
- 2,168 of 2,184 investment rows (99.3%) parsed into structured fields
- Remaining 16 rows — FX forward contracts, cash-equivalent summary lines, and a small number of rows with source-level data gaps — are out of scope for Phase 1 and flagged for Phase 3 (AI-assisted normalization)
- Output: `data/processed/bxsl_2026q1_parsed.csv`, `data/processed/bxsl_2026q1_unmatched.csv`

**Design principle**: Long-tail row patterns beyond a reasonable point are intentionally not hardcoded further. Instead of chasing an ever-growing list of edge cases, remaining unmatched rows are handed off to an AI normalization layer (Phase 3) — a deliberate architectural choice, not a shortcut.

### Phase 2: Multi-Quarter Time-Series Pipeline — Complete

**Scope**: Extend the Phase 1 parser across multiple historical filings to build a time series of BXSL's portfolio positions, tagged by true reporting period rather than SEC submission date.

**What was built**:
- `src/pipeline.py` — orchestrates fetching, parsing, and persisting filings across multiple quarters, with per-filing error isolation so one failed filing doesn't halt the pipeline
- `data/bdc_tracker.db` (sqlite) — stores parsed positions (`positions` table) and unmatched rows (`unmatched_positions` table) across all quarters

**Two data-integrity bugs found and fixed during this phase**:
1. **Comparative prior-period contamination**: BDC 10-Q/10-K filings include both the current period's Schedule of Investments *and* a comparative prior-period schedule in the same document (e.g. "as of March 31, 2026 and December 31, 2025"). The initial pipeline tagged both with the same `filing_date`, causing duplicate/conflicting fair values for the same position. Fixed by extracting each table's true as-of date from its title block and filtering to the current period only — identified via the filing document's own filename (e.g. `bxsl-20250930.htm` → period end `2025-09-30`), which is more reliable than the SEC submission date.
2. **Silent misclassification from missing fields**: A row with a missing `acquisition_date` field collapsed to the same token count as a fixed-rate debt row, causing every subsequent value to shift into the wrong column. Fixed by adding a floating-rate marker check (e.g. presence of "SOFR +") before accepting the fixed-rate schema match — rows that don't cleanly fit are now routed to `unmatched` instead of being silently parsed incorrectly.

**Results**:
- 8 quarters parsed (2024-06-30 through 2026-03-31)
- 6,948 total positions persisted to sqlite
- 83 unmatched rows across all quarters, consistent with Phase 1's long-tail categories (FX forwards, cash equivalents, unfunded commitments)

**Known issue carried into Phase 3**: Portfolio companies that are renamed/rebranded mid-filing history (e.g. a second lien tranche appearing under a different legal entity name in earlier quarters) are currently tracked as separate positions rather than being linked as the same underlying investment. This is a good candidate for the AI normalization layer.

### Next: Phase 3 — Event Detection + AI Normalization Layer
Detect entry/exit/markdown events across the time series, and introduce an AI-assisted normalization layer (column/industry standardization, company name reconciliation) for the long-tail rows that fall outside the deterministic parser's coverage.