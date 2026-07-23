"""
edgar_client.py
Handles all communication with the SEC EDGAR API.
- Fetches a company's filing history
- Filters filings by form type (10-Q, 10-K, etc.)
- Builds direct URLs to the actual filing documents
"""

import re
import time
import requests
from datetime import datetime

from config import SEC_USER_AGENT, SEC_BASE_URL


def _get_headers() -> dict:
    """SEC requires a descriptive User-Agent header, or requests get blocked."""
    return {"User-Agent": SEC_USER_AGENT}


def get_company_submissions(cik: str) -> dict:
    """
    Fetch the full filing history summary for a given company.
    `cik` must be a 10-digit, zero-padded string (e.g. "0001736035").
    """
    url = f"{SEC_BASE_URL}/submissions/CIK{cik}.json"
    response = requests.get(url, headers=_get_headers())
    response.raise_for_status()  # fail loudly instead of silently swallowing errors
    return response.json()


def get_recent_filings(cik: str, form_types: list[str] = None, limit: int = 8) -> list[dict]:
    """
    Return the most recent filings for a company, filtered by form type.
    Defaults to 10-Q and 10-K.

    Returns a list of dicts: {cik, accession_number, filing_date, form, primary_document}
    Ordered most-recent-first (as returned by SEC).
    """
    if form_types is None:
        form_types = ["10-Q", "10-K"]

    data = get_company_submissions(cik)
    recent = data["filings"]["recent"]

    # SEC returns column-oriented data (parallel lists), so we zip them
    # back into row-based records using the shared index.
    results = []
    for i, form in enumerate(recent["form"]):
        if form in form_types:
            results.append({
                "cik": cik,
                "accession_number": recent["accessionNumber"][i],
                "filing_date": recent["filingDate"][i],
                "form": form,
                "primary_document": recent["primaryDocument"][i],
            })
        if len(results) >= limit:
            break

    return results


def build_document_url(cik: str, accession_number: str, primary_document: str) -> str:
    """
    Build a direct URL to the actual filing document (HTML).
    Note: dashes must be stripped from the accession number, and
    leading zeros must be stripped from the CIK for the URL path to work.
    """
    accession_no_dashes = accession_number.replace("-", "")
    cik_no_leading_zeros = str(int(cik))
    return (
        f"https://www.sec.gov/Archives/edgar/data/"
        f"{cik_no_leading_zeros}/{accession_no_dashes}/{primary_document}"
    )


def fetch_filing_html(document_url: str) -> str:
    """Fetch the raw HTML content of a filing document."""
    response = requests.get(document_url, headers=_get_headers())
    response.raise_for_status()
    time.sleep(0.2)  # be polite to SEC's rate limit (~10 requests/sec)
    return response.text


def extract_period_end_date(primary_document: str) -> str | None:
    """
    Extract the true reporting period-end date encoded in the filing's
    primary document filename (e.g. 'bxsl-20250930.htm' -> '2025-09-30').
    This is more reliable than the SEC filing_date, which is when the
    document was submitted — typically 5-6 weeks AFTER the period end,
    and NOT the date the Schedule of Investments is "as of".
    """
    match = re.search(r"(\d{8})", primary_document)
    if not match:
        return None
    return datetime.strptime(match.group(1), "%Y%m%d").strftime("%Y-%m-%d")


if __name__ == "__main__":
    # Quick sanity check — print BXSL's most recent 10-Q filings
    from config import BXSL_CIK

    filings = get_recent_filings(BXSL_CIK, form_types=["10-Q"], limit=3)
    for f in filings:
        url = build_document_url(f["cik"], f["accession_number"], f["primary_document"])
        print(f"{f['filing_date']} | {f['form']} | {url}")