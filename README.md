# BDC Portfolio Tracker — AI Integration Framework

## Project Context
- Data source: SEC EDGAR (BDC quarterly Schedule of Investments)
- Target company: BXSL (Blackstone Secured Lending) — starting point
- Core financial calculations (IRR, MOIC, mark-to-market changes) remain deterministic (pandas/pyxirr) — AI is never used for core financial math.

## Tech Stack

| Purpose | Tool/Library |
|---|---|
| API requests | `requests` |
| HTML/table parsing | `beautifulsoup4`, `pandas.read_html()` |
| Data cleaning/structuring | `pandas` |
| IRR/MOIC calculation | `pyxirr` |
| Storage | `sqlite3` or local `parquet` |
| Dashboard/visualization | `streamlit`, `plotly` |
| AI integration layer | Claude API (column normalization, footnote extraction, commentary generation) |
| Dev workflow | Claude Code (iterative parser debugging across filings) |

## Relevance to HSBC Alternatives Transformation BA Role

| Project Component | JD Requirement |
|---|---|
| `SOI parsing`, `IRR/MOIC calculation` | Strong data analysis and reporting skills, including SQL and analytical tools |
| `Column normalization`, `validation layer` | Ensure robust data governance and data quality standards across the Alternatives platform |
| `Deal-level BDC portfolio structure`, `mark-to-market tracking` | Deep understanding of private markets (private credit, real assets) |
| `Deterministic vs. AI-scoped architecture design` | Experience with emerging technologies (AI/ML) in alternatives context |
| `Quarterly commentary generation` | Solution design for valuation and reporting solutions |
| `End-to-end pipeline (raw filing → structured data → dashboard)` | Translate business requirements into scalable, compliant system designs |

## Where AI Fits in the Workflow

### 1. Schedule of Investments Column Normalization
- **Problem**: Column headers vary across filings and BDCs (e.g. "Fair Value" vs "FV (000s)" vs "Fair Value ($000)")
- **AI role**: Map raw column headers to a standard schema (`company`, `industry`, `investment_type`, `cost`, `fair_value`, `coupon_rate`)
- **Why it matters**: Directly addresses data governance / data quality standards requirement

### 2. Footnote & Narrative Disclosure Extraction
- **Problem**: Non-accrual status, restructuring, covenant breach info is buried in narrative text, not tables
- **AI role**: Extract structured risk signals (company name, issue type, reason) from filing text
- **Why it matters**: Surfaces qualitative risk signals that regex/rule-based parsing can't reliably catch

### 3. Industry Classification Standardization
- **Problem**: Each BDC uses inconsistent industry tags (e.g. "Software" vs "Technology Services" vs "IT Solutions")
- **AI role**: Map to a standard taxonomy (GICS-like) to enable cross-BDC sector exposure comparison

### 4. Automated Quarterly Commentary Generation
- **Problem**: After IRR/MOIC/markdown events are calculated, summarizing key changes is time-consuming
- **AI role**: Generate LP-report-style narrative summaries from the computed structured data (post-calculation only)
- **Why it matters**: Maps to valuation and reporting solutions requirement

### 5. Parsing Sanity-Check Layer
- **Problem**: Parsed tables may silently misalign with source text
- **AI role**: Secondary validation layer — cross-check parsed table output against source text for logical consistency
- **Note**: Supplementary to deterministic validation rules (date ordering, value ranges), not a replacement

## Development Workflow

- **Claude Code usage**: Iteratively handle parsing edge cases across BDCs/quarters where HTML table structure varies — automate detection of parsing failures and refine parser logic at scale rather than manual case-by-case debugging

## Guiding Principle

- Deterministic code owns all core financial calculations (IRR, MOIC, valuation math)
- AI is scoped strictly to: (a) unstructured → structured transformation, and (b) structured → natural language summarization
- This separation is itself the interview talking point: knowing *where* AI should and shouldn't be used in a financial data pipeline

