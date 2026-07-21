"""
parser.py
Parses the Schedule of Investments table from a BDC's 10-Q/10-K filing HTML
into a clean, row-based pandas DataFrame.

Key challenge: the raw table encodes company/industry grouping as ROW
HIERARCHY (section header rows), not as separate columns. This module
walks the table top to bottom, tracking the current debt type and
industry, and tags each investment row accordingly.
"""

from bs4 import BeautifulSoup
import pandas as pd

# Column order as it appears in BXSL's Schedule of Investments table.
# NOTE: verify this against each new filing — BDCs occasionally add/reorder columns.
EXPECTED_COLUMNS = [
    "investment_name",
    "footnotes",
    "reference_rate_and_spread",
    "interest_rate",
    "acquisition_date",
    "maturity_date",
    "par_amount_units",
    "cost",
    "fair_value",
    "pct_of_net_assets",
]


def find_schedule_of_investments_tables(html: str) -> list:
    """
    Locate the table(s) that make up the Schedule of Investments section.
    Filings often split this into multiple <table> elements (one per
    debt type: First Lien, Second Lien, Equity, etc.), so this returns
    a list, not a single table.
    """
    soup = BeautifulSoup(html, "lxml")

    # Anchor search: find a heading that mentions "Schedule of Investments",
    # then collect the tables that follow it up to the next major heading.
    # This is filing-specific and WILL need adjustment once we test against
    # a real document — treat this as a starting point, not a final answer.
    candidates = []
    for heading in soup.find_all(string=lambda s: s and "Schedule of Investments" in s):
        parent = heading.find_parent()
        table = parent.find_next("table") if parent else None
        if table:
            candidates.append(table)

    return candidates


def _row_cells(tr) -> list[str]:
    """Extract stripped text from every cell in a table row."""
    return [cell.get_text(strip=True) for cell in tr.find_all(["td", "th"])]


def _is_section_header(cells: list[str]) -> bool:
    """
    Heuristic: a section header row (e.g. 'First Lien Debt', 'Aerospace & Defense')
    has text in the first cell and is blank everywhere else.
    """
    non_empty = [c for c in cells if c]
    return len(non_empty) == 1 and cells[0] != ""


def _is_subtotal_row(cells: list[str]) -> bool:
    """
    Heuristic: a subtotal row has NO investment name (first cell blank)
    but DOES have numeric values in the cost/fair value/% columns.
    Adjust the index checks once we confirm actual column positions.
    """
    if not cells or cells[0] != "":
        return False
    return any(c.replace(",", "").replace("$", "").strip().isdigit() for c in cells if c)


def parse_table(table) -> pd.DataFrame:
    """
    Walk a single Schedule of Investments table and return a tidy DataFrame
    with hierarchy (debt_type, industry) forward-filled onto each data row.
    """
    rows = []
    current_debt_type = None
    current_industry = None

    for tr in table.find_all("tr"):
        cells = _row_cells(tr)
        if not cells:
            continue

        if _is_section_header(cells):
            # Rough heuristic for now: assume top-level debt type vs. industry
            # based on known keywords. This WILL need refinement once we see
            # more real examples (equity sections, second lien, etc.).
            label = cells[0]
            if "Debt" in label or "Equity" in label:
                current_debt_type = label
            else:
                current_industry = label
            continue

        if _is_subtotal_row(cells):
            # Skip subtotal rows for now — we recompute totals ourselves
            # from the underlying data rows, so we don't need to trust
            # the filing's own subtotal formatting.
            continue

        # Otherwise: treat as a data row
        row_data = {
            "debt_type": current_debt_type,
            "industry": current_industry,
        }
        # Zip cells to expected columns where possible; pad/truncate as needed
        for i, col_name in enumerate(EXPECTED_COLUMNS):
            row_data[col_name] = cells[i] if i < len(cells) else None

        rows.append(row_data)

    return pd.DataFrame(rows)


def parse_filing_html(html: str) -> pd.DataFrame:
    """
    Full pipeline: find all Schedule of Investments tables in a filing
    and combine them into a single DataFrame.
    """
    tables = find_schedule_of_investments_tables(html)
    all_rows = [parse_table(t) for t in tables]
    return pd.concat(all_rows, ignore_index=True) if all_rows else pd.DataFrame()