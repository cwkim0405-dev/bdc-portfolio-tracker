"""
parser.py
Parses the Schedule of Investments table from a BDC's 10-Q/10-K filing HTML
into a clean, row-based pandas DataFrame.

Key filing quirks handled here:
- "$" and "%" symbols are only rendered on the first row of a contiguous
  block, then omitted on subsequent rows — purely cosmetic, safe to drop.
- Table cells are interleaved with empty spacer cells for HTML alignment.
- Category/industry headers can span multiple physical tables, marked
  with "(continued)" when a section carries over to a new page.
"""

import re
from bs4 import BeautifulSoup
import pandas as pd

# Standard field order for a floating-rate debt row, once empty cells
# and cosmetic $ / % symbols have been stripped out.
# 3-letter ISO currency codes we expect to see in non-USD denominated rows
KNOWN_CURRENCY_CODES = {
    "USD", "EUR", "GBP", "SEK", "DKK", "NOK", "CHF", "JPY", "AUD", "CAD",
    "NZD", "SGD", "HKD", "MXN", "BRL", "ZAR", "INR", "CNY", "KRW", "PLN",
    "CZK", "HUF", "TRY", "ILS", "AED", "SAR",
    # extend this list if a filing surfaces a code not covered here —
    # unmatched rows will surface it for review rather than failing silently
}

def _extract_currency(tokens: list[str]) -> tuple[str, list[str]]:
    """
    Find a known ISO currency code among the tokens and remove it,
    returning (currency, remaining_tokens). Defaults to USD when no
    explicit code is present (USD is omitted in the filing by convention).
    """
    for i, tok in enumerate(tokens):
        if tok in KNOWN_CURRENCY_CODES:
            return tok, tokens[:i] + tokens[i + 1:]
    return "USD", tokens

FLOATING_RATE_FIELDS = [
    "investment_name", "footnotes", "reference_rate_base", "spread",
    "interest_rate", "acquisition_date", "maturity_date",
    "par_amount", "cost", "fair_value", "pct_of_net_assets",
]  # 11 tokens after currency removed

FIXED_RATE_FIELDS = [
    "investment_name", "footnotes", "stated_rate", "interest_rate",
    "acquisition_date", "maturity_date",
    "par_amount", "cost", "fair_value", "pct_of_net_assets",
]


def _is_total_row(tokens: list[str]) -> bool:
    """
    Rows like 'Total First Lien Debt - non-controlled/non-affiliated' are
    category-level totals (not per-industry subtotals, which have no name
    at all). We recompute totals from data rows ourselves, so skip these.
    """
    return bool(tokens) and tokens[0].startswith("Total ")

EQUITY_FIELDS = [
    "investment_name", "footnotes", "acquisition_date",
    "units", "cost", "fair_value", "pct_of_net_assets",
]  # 7 tokens after currency removed — no rate/maturity, since equity has neither

PREFERRED_EQUITY_FIELDS = [
    "investment_name", "footnotes", "dividend_rate", "acquisition_date",
    "units", "cost", "fair_value", "pct_of_net_assets",
]  # 8 tokens — equity row with a stated dividend/preferred rate

UNFUNDED_COMMITMENT_FIELDS = [
    "investment_name", "commitment_type", "maturity_date",
    "par_amount", "unrealized_gain_loss",
]  # 5 tokens — unfunded revolver/delayed draw commitments; no footnotes, rate, or cost basis

def find_schedule_of_investments_tables(html: str) -> list:
    """Locate every <table> that is part of the Schedule of Investments section."""
    soup = BeautifulSoup(html, "lxml")
    candidates = []
    for heading in soup.find_all(string=lambda s: s and "Schedule of Investments" in s):
        parent = heading.find_parent()
        table = parent.find_next("table") if parent else None
        if table:
            candidates.append(table)
    return candidates


def _row_cells(tr) -> list[str]:
    """Extract stripped text from every cell in a table row (raw, unfiltered)."""
    return [cell.get_text(strip=True) for cell in tr.find_all(["td", "th"])]


def _clean_tokens(cells: list[str]) -> list[str]:
    """
    Drop empty spacer cells and cosmetic currency/percent symbols that
    are only shown once per block. What remains is the real data, in order.
    """
    return [c for c in cells if c not in ("", "$", "%")]


def _is_section_header(raw_cells: list[str], tokens: list[str]) -> bool:
    """A section header (debt type or industry name) has exactly one real token."""
    return len(tokens) == 1 and raw_cells and raw_cells[0] != ""


def _is_subtotal_row(raw_cells: list[str], tokens: list[str]) -> bool:
    """A subtotal row has no investment name but has 2-3 trailing numeric tokens."""
    has_no_name = not raw_cells or raw_cells[0] == ""
    return has_no_name and 2 <= len(tokens) <= 3


def _clean_category_label(label: str) -> str:
    """Strip the '(continued)' suffix so sections spanning multiple pages merge correctly."""
    return re.sub(r"\s*\(continued\)\s*$", "", label).strip()


def _is_column_header_row(tokens: list[str]) -> bool:
    """The literal column header row (e.g. 'Investments', 'Footnotes', 'Cost'...)
    repeats once per page in the filing — filter it out as noise."""
    return bool(tokens) and tokens[0].startswith("Investments")


def parse_all_tables(tables: list) -> pd.DataFrame:
    """
    Walk every Schedule of Investments table IN ORDER, carrying category
    state (debt_type, industry) across table boundaries — this matters
    because a single logical section can be split across several tables
    when it spans a page break in the filing.
    """
    rows = []
    current_debt_type = None
    current_industry = None
    unmatched_count = 0

    for table in tables:
        for tr in table.find_all("tr"):
            raw_cells = _row_cells(tr)
            if not raw_cells:
                continue

            tokens = _clean_tokens(raw_cells)
            if not tokens:
                continue

            if _is_column_header_row(tokens):
                continue
            
            if _is_section_header(raw_cells, tokens):
                label = _clean_category_label(tokens[0])
                if "Debt" in label or "Equity" in label:
                    current_debt_type = label
                else:
                    current_industry = label
                continue

            if _is_subtotal_row(raw_cells, tokens):
                # Subtotals are recomputed from data rows later — skip for now.
                continue

            if _is_total_row(tokens):
                continue  # category-level total, not a real position

            currency, remaining = _extract_currency(tokens)

            if len(remaining) == 11:
                row_data = dict(zip(FLOATING_RATE_FIELDS, remaining))
            elif len(remaining) == 10:
                row_data = dict(zip(FIXED_RATE_FIELDS, remaining))
            elif len(remaining) == 8:
                row_data = dict(zip(PREFERRED_EQUITY_FIELDS, remaining))
            elif len(remaining) == 7:
                row_data = dict(zip(EQUITY_FIELDS, remaining))
            elif len(remaining) == 5:
                row_data = dict(zip(UNFUNDED_COMMITMENT_FIELDS, remaining))
            else:
                unmatched_count += 1
                rows.append({
                    "debt_type": current_debt_type,
                    "industry": current_industry,
                    "raw_tokens": tokens,
                    "raw_cells": raw_cells,  # keep the untouched cells too — 
                                              # useful context for the AI classifier later
                })
                continue

            row_data["currency"] = currency
            row_data["debt_type"] = current_debt_type
            row_data["industry"] = current_industry
            rows.append(row_data)

    if unmatched_count:
        print(f"[parser] {unmatched_count} rows didn't match the standard "
              f"debt-row pattern — check the 'raw_tokens' column for those rows.")

    return pd.DataFrame(rows)


def parse_filing_html(html: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Returns (parsed_df, unmatched_df) — separating cleanly parsed positions
    from rows that need AI-assisted classification (Phase 3) or manual review.
    """
    tables = find_schedule_of_investments_tables(html)
    df = parse_all_tables(tables)
    
    parsed = df[df["raw_tokens"].isna()].drop(columns=["raw_tokens", "raw_cells"], errors="ignore")
    unmatched = df[df["raw_tokens"].notna()][["debt_type", "industry", "raw_tokens", "raw_cells"]]
    
    return parsed, unmatched