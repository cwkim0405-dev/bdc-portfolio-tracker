"""
metrics.py
Numeric cleanup and derived metrics (IRR/MOIC, event detection) built on
top of the parsed time-series data in data/bdc_tracker.db.
"""

import pandas as pd

from src.normalizer import normalize_entity_name


def clean_numeric_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert filing-formatted numeric strings (e.g. '46,713', '(9)' for
    negative, '—' for zero/none) into actual numeric types.
    """
    df = df.copy()
    numeric_cols = ["par_amount", "cost", "fair_value", "pct_of_net_assets", "units"]

    for col in numeric_cols:
        if col not in df.columns:
            continue
        df[col] = (
            df[col]
            .astype(str)
            .str.replace(",", "", regex=False)
            .str.replace("—", "0", regex=False)
            .str.replace(r"^\((.+)\)$", r"-\1", regex=True)  # (9) -> -9
        )
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def detect_events(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["position_key"] = (
        df["investment_name"].apply(normalize_entity_name)
        + " | " + df["acquisition_date"].astype(str)
    )

    # A (period, position_key) pair should be unique, but multiple tranches
    # can share the same company + acquisition date (e.g. different
    # investment types drawn on the same day) — aggregate fair_value by
    # summing, so each (period, position_key) maps to exactly one row.
    grouped = (
        df.groupby(["period_end_date", "position_key"], as_index=False)
        .agg(
            fair_value=("fair_value", "sum"),
            investment_name=("investment_name", "first"),  # representative label for display
        )
    )

    periods = sorted(grouped["period_end_date"].dropna().unique())
    events = []

    for i in range(1, len(periods)):
        prev_period, curr_period = periods[i - 1], periods[i]

        prev_positions = grouped[grouped["period_end_date"] == prev_period].set_index("position_key")
        curr_positions = grouped[grouped["period_end_date"] == curr_period].set_index("position_key")

        prev_keys = set(prev_positions.index)
        curr_keys = set(curr_positions.index)

        for key in curr_keys - prev_keys:
            row = curr_positions.loc[key]
            events.append({
                "position_key": key,
                "investment_name": row["investment_name"],
                "event_type": "new_entry",
                "period_end_date": curr_period,
                "fair_value": row["fair_value"],
            })

        for key in prev_keys - curr_keys:
            row = prev_positions.loc[key]
            events.append({
                "position_key": key,
                "investment_name": row["investment_name"],
                "event_type": "exit",
                "period_end_date": curr_period,
                "fair_value": 0,
            })

        for key in curr_keys & prev_keys:
            prev_fv = prev_positions.loc[key, "fair_value"]
            curr_fv = curr_positions.loc[key, "fair_value"]

            if pd.isna(prev_fv) or pd.isna(curr_fv) or prev_fv == 0:
                continue

            pct_change = (curr_fv - prev_fv) / prev_fv
            if abs(pct_change) >= 0.10:
                events.append({
                    "position_key": key,
                    "investment_name": curr_positions.loc[key, "investment_name"],
                    "event_type": "markdown" if pct_change < 0 else "markup",
                    "period_end_date": curr_period,
                    "fair_value": curr_fv,
                    "pct_change": round(pct_change * 100, 1),
                })

    return pd.DataFrame(events)