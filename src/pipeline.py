"""
pipeline.py
Orchestrates Phase 2: fetch multiple historical filings for a company,
parse each one (current-period tables only), tag rows with their true
reporting period-end date, and persist the combined time series to sqlite.
"""

from pathlib import Path
import sqlite3
import json
import pandas as pd

from src.edgar_client import get_recent_filings, build_document_url, fetch_filing_html, extract_period_end_date
from src.parser import parse_filing_html

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "bdc_tracker.db"


def build_time_series(cik: str, form_types: list[str] = None, limit: int = 8) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Fetch and parse the last `limit` filings for a company, tagging every
    row with its true period_end_date (derived from the filing document
    name, NOT the SEC submission filing_date) so positions can be tracked
    across quarters without prior-period comparative data bleeding in.
    """
    filings = get_recent_filings(cik, form_types=form_types, limit=limit)

    all_parsed = []
    all_unmatched = []

    for f in filings:
        url = build_document_url(f["cik"], f["accession_number"], f["primary_document"])
        period_end = extract_period_end_date(f["primary_document"])
        print(f"Fetching {f['filing_date']} ({f['form']}), period end: {period_end}...")

        if period_end is None:
            print(f"  Skipped {f['filing_date']}: couldn't determine period end date")
            continue

        try:
            html = fetch_filing_html(url)
            parsed, unmatched = parse_filing_html(html, target_period_end=period_end)
        except Exception as e:
            print(f"  Skipped {f['filing_date']}: {e}")
            continue

        parsed = parsed.copy()
        parsed["period_end_date"] = period_end
        parsed["filing_date"] = f["filing_date"]  # kept for audit/reference only
        parsed["accession_number"] = f["accession_number"]
        all_parsed.append(parsed)

        unmatched = unmatched.copy()
        unmatched["period_end_date"] = period_end
        unmatched["filing_date"] = f["filing_date"]
        unmatched["accession_number"] = f["accession_number"]
        all_unmatched.append(unmatched)

    parsed_combined = pd.concat(all_parsed, ignore_index=True) if all_parsed else pd.DataFrame()
    unmatched_combined = pd.concat(all_unmatched, ignore_index=True) if all_unmatched else pd.DataFrame()

    return parsed_combined, unmatched_combined


def save_to_sqlite(parsed_df: pd.DataFrame, unmatched_df: pd.DataFrame, db_path=DB_PATH):
    """Persist both tables to sqlite, replacing any existing data."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # sqlite can't store Python list objects directly — serialize list-typed
    # columns (raw_tokens, raw_cells) to JSON strings before saving.
    unmatched_to_save = unmatched_df.copy()
    for col in ("raw_tokens", "raw_cells"):
        if col in unmatched_to_save.columns:
            unmatched_to_save[col] = unmatched_to_save[col].apply(
                lambda x: json.dumps(x) if isinstance(x, list) else x
            )

    conn = sqlite3.connect(db_path)
    parsed_df.to_sql("positions", conn, if_exists="replace", index=False)
    unmatched_to_save.to_sql("unmatched_positions", conn, if_exists="replace", index=False)
    conn.close()
    print(f"Saved {len(parsed_df)} parsed rows and {len(unmatched_df)} unmatched rows to {db_path}")


if __name__ == "__main__":
    from config import BXSL_CIK

    parsed, unmatched = build_time_series(BXSL_CIK, form_types=["10-Q", "10-K"], limit=8)
    save_to_sqlite(parsed, unmatched)