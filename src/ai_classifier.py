"""
ai_classifier.py
AI-assisted classification for the long-tail "unmatched" rows that the
deterministic parser (parser.py) couldn't cleanly fit into a known schema.

Cost-conscious by design:
- classify_unmatched_rows() defaults to a small sample (sample_size=15) —
  full-scale runs require an explicit sample_size=None.
- Actual token usage (from the API response, not estimated) is printed
  after every batch and summed at the end, so cost is always visible
  before scaling up.
- The instruction prompt is marked for prompt caching, so repeated calls
  within a session reuse the cached (90% cheaper) version of the
  unchanging instructions instead of re-paying full price every batch.
"""

import json
import time

import anthropic
import pandas as pd

from config import ANTHROPIC_API_KEY

CLIENT = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
MODEL = "claude-sonnet-4-5"

BATCH_SIZE = 15

# Anthropic list pricing per million tokens, as of mid-2026. Update these
# if pricing changes — see https://claude.com/pricing for current rates.
PRICE_PER_M_INPUT = 3.00
PRICE_PER_M_OUTPUT = 15.00

# Static instructions, kept separate from the per-batch data so they can be
# marked with cache_control — Anthropic charges only ~10% of the input
# price for cached content on repeat calls within the cache's TTL.
CLASSIFICATION_INSTRUCTIONS = """You are helping classify rows from a Business Development Company's (BDC) Schedule of Investments filing that a rules-based parser could not confidently structure.

For each row below, you are given:
- debt_type: the broader category label active when this row appeared (may be null)
- industry: the industry label active when this row appeared (may be null)
- raw_tokens: the actual cell values from the filing row, in their original left-to-right order

Classify each row into ONE of these investment_type categories:
- "fx_forward": a foreign currency forward contract (bank counterparty, two currency amounts, a settlement date, and an unrealized appreciation/depreciation figure)
- "interest_rate_swap": a swap contract (counterparty, hedged item/notes reference, receive/pay rates, notional amount, maturity date, fair market value)
- "money_market_fund": a short-term cash-equivalent fund position (fund name, a yield/rate, and cost/fair value)
- "equity_or_debt_with_gaps": looks like a normal equity or debt position, but is missing one or more expected fields (e.g. no acquisition date)
- "other": doesn't fit any of the above — explain briefly in the "notes" field

Extract whatever standard fields you can confidently identify. Use these field names precisely — do not substitute a similarly-named field:
- investment_name, counterparty, currency
- par_amount, cost
- fair_value: the investment's current worth (for debt/equity positions only — NOT for derivatives)
- unrealized_gain_loss: mark-to-market P&L (for FX forwards and interest rate swaps — this is a DIFFERENT concept from fair_value and must never be placed in the fair_value field)
- currency_purchased_amount, currency_purchased_code, currency_sold_amount, currency_sold_code: for FX forwards specifically, extract the two currency legs as separate structured numeric fields, not just in notes
- notional_amount: for interest rate swaps
- pct_of_net_assets, settlement_date (for FX forwards), maturity_date (for swaps/debt — NOT the same as settlement_date), acquisition_date

Use null for any field you cannot confidently determine — do NOT guess or fabricate a value, and do NOT place a value in a semantically wrong field (e.g. never put a settlement date in maturity_date, never put unrealized P&L in fair_value).

Return ONLY a JSON array, one object per input row, in the same order as the input. Each object must have this shape:
{"investment_type": "...", "investment_name": null, "counterparty": null, "currency": null, "par_amount": null, "cost": null, "fair_value": null, "unrealized_gain_loss": null, "currency_purchased_amount": null, "currency_purchased_code": null, "currency_sold_amount": null, "currency_sold_code": null, "notional_amount": null, "pct_of_net_assets": null, "settlement_date": null, "maturity_date": null, "acquisition_date": null, "notes": "..."}"""


def _estimate_cost(usage) -> float:
    """Compute actual USD cost for one API call from its reported token usage."""
    input_cost = (usage.input_tokens / 1_000_000) * PRICE_PER_M_INPUT
    output_cost = (usage.output_tokens / 1_000_000) * PRICE_PER_M_OUTPUT
    return input_cost + output_cost


def _classify_batch(rows: list[dict]) -> tuple[list[dict], float]:
    """Send one batch to Claude, return (parsed_results, actual_cost_usd)."""
    rows_json = json.dumps(rows, indent=2)

    response = CLIENT.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=[
            {
                "type": "text",
                "text": CLASSIFICATION_INSTRUCTIONS,
                "cache_control": {"type": "ephemeral"},  # cache the static instructions
            }
        ],
        messages=[{"role": "user", "content": f"Input rows:\n{rows_json}"}],
    )

    cost = _estimate_cost(response.usage)

    text = response.content[0].text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("\n") + 1:] if "\n" in text else text
        if text.endswith("json"):
            text = text[:-4]

    try:
        return json.loads(text), cost
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse AI response as JSON: {e}\nRaw response:\n{text}")


def classify_unmatched_rows(unmatched_df: pd.DataFrame, sample_size: int | None = 15) -> pd.DataFrame:
    """
    Classify unmatched rows using Claude, in batches.

    sample_size: number of rows to process. Defaults to a SMALL SAMPLE (15)
    as a deliberate safety default — always test on a sample before running
    the full dataset. Pass sample_size=None explicitly to process everything.
    """
    df = unmatched_df if sample_size is None else unmatched_df.head(sample_size)
    rows = df.to_dict(orient="records")

    if sample_size is not None:
        print(f"[SAMPLE MODE] Processing {len(rows)} of {len(unmatched_df)} rows. "
              f"Pass sample_size=None to run the full dataset.")

    results = []
    total_cost = 0.0

    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        batch_input = [
            {
                "debt_type": r.get("debt_type"),
                "industry": r.get("industry"),
                "raw_tokens": json.loads(r["raw_tokens"]) if isinstance(r["raw_tokens"], str) else r["raw_tokens"],
            }
            for r in batch
        ]

        print(f"Classifying rows {i}-{i + len(batch) - 1} of {len(rows)}...")
        classified, batch_cost = _classify_batch(batch_input)
        total_cost += batch_cost
        print(f"  Batch cost: ${batch_cost:.4f} (running total: ${total_cost:.4f})")

        if len(classified) != len(batch):
            print(f"  Warning: expected {len(batch)} results, got {len(classified)} — skipping this batch")
            continue

        for original, result in zip(batch, classified):
            merged = {**result}
            merged["period_end_date"] = original.get("period_end_date")
            merged["filing_date"] = original.get("filing_date")
            merged["accession_number"] = original.get("accession_number")
            results.append(merged)

        time.sleep(0.5)

    print(f"\nTotal API cost for this run: ${total_cost:.4f}")
    return pd.DataFrame(results)