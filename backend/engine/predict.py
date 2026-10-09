"""Prediction engine: demand forecast + reorder recommendation per SKU.

Pure pandas/numpy, no Django dependency, so it can be unit-tested and
backtested on its own and imported by the API layer later.

Information rule: for an `as_of` date, only transactions dated <= as_of are
used (no leakage from the future).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np
import pandas as pd

Z_SERVICE = 1.65          # ~95% cycle service level
REVIEW_DAYS = 7           # how often the owner reviews / places orders
WINDOW_DAYS = 28          # recent window for the demand estimate
MIN_HISTORY_DAYS = 14     # below this we flag cold start
TARGET_COVER_DAYS = 14    # order up to this many days of cover beyond lead time


@dataclass
class Recommendation:
    sku: str
    as_of: str
    stock_on_hand: int
    daily_demand: float
    demand_std: float
    lead_time_days: int
    reorder_point: float
    days_of_cover: float | None
    should_reorder: bool
    recommended_qty: int
    urgency: str            # urgent | soon | ok
    confidence: str         # high | low
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


def load_data(data_dir: str | Path):
    data_dir = Path(data_dir)
    products = pd.read_csv(data_dir / "products.csv")
    txns = pd.read_csv(data_dir / "transactions.csv", parse_dates=["date"])
    return products, txns


def stock_as_of(sku: str, as_of: pd.Timestamp, products: pd.DataFrame,
                txns: pd.DataFrame, clamp: bool = True) -> int:
    """Reconstruct stock on hand at end of `as_of` by rolling back later activity.

    Known gap: the demo scenario for SNK-001 trims `current_stock` directly, so
    its history does not reconcile and rolling back can go negative. With
    clamp=True (default) the result is floored at 0; pass clamp=False to see
    the raw value. Real fix: export opening stock or an adjustment row.
    """
    current = int(products.loc[products.sku == sku, "current_stock"].iloc[0])
    later = txns[(txns.sku == sku) & (txns.date > as_of)]
    sold = later.loc[later.type == "SALE", "quantity"].sum()
    restocked = later.loc[later.type == "RESTOCK", "quantity"].sum()
    raw = int(current + sold - restocked)
    return max(0, raw) if clamp else raw


def daily_sales(sku: str, as_of: pd.Timestamp, txns: pd.DataFrame) -> pd.Series:
    s = txns[(txns.sku == sku) & (txns.type == "SALE") & (txns.date <= as_of)]
    if s.empty:
        return pd.Series(dtype=float)
    daily = s.groupby("date")["quantity"].sum()
    full = pd.date_range(daily.index.min(), as_of, freq="D")
    return daily.reindex(full, fill_value=0).astype(float)


def recommend(sku: str, as_of, products: pd.DataFrame,
              txns: pd.DataFrame) -> Recommendation:
    as_of = pd.Timestamp(as_of)
    prod = products.loc[products.sku == sku].iloc[0]
    lead = int(prod.reorder_lead_time_days)
    series = daily_sales(sku, as_of, txns)
    stock = stock_as_of(sku, as_of, products, txns)
    history_days = len(series)

    recent = series.tail(WINDOW_DAYS)
    if recent.empty:
        rate, std = 0.0, 0.0
    else:
        # exponentially weighted so recent days count more
        rate = float(recent.ewm(halflife=10).mean().iloc[-1])
        std = float(recent.std(ddof=0))

    horizon = lead + REVIEW_DAYS
    lead_demand = rate * horizon
    safety = Z_SERVICE * std * np.sqrt(horizon)
    reorder_point = lead_demand + safety
    cover = stock / rate if rate > 0 else None

    should = stock <= reorder_point
    qty = 0
    if should:
        target = reorder_point + rate * TARGET_COVER_DAYS
        qty = int(max(0, np.ceil(target - stock)))

    if cover is not None and cover <= lead:
        urgency = "urgent"
    elif should:
        urgency = "soon"
    else:
        urgency = "ok"

    confidence = "low" if history_days < MIN_HISTORY_DAYS else "high"

    if history_days == 0:
        reason = (f"{prod['name']} has no sales history yet, so no forecast is "
                  f"possible. {stock} units on hand; revisit once it has at "
                  f"least {MIN_HISTORY_DAYS} days of sales.")
    elif rate == 0:
        reason = (f"No recent sales for {prod['name']}; holding steady with "
                  f"{stock} units on hand.")
    elif urgency == "urgent":
        reason = (f"{prod['name']} sells about {rate:.1f}/day and {stock} are "
                  f"left (~{cover:.1f} days). Supplier takes {lead} days, so "
                  f"you'd run out before a new order arrives. Order {qty} to "
                  f"cover the lead time plus {TARGET_COVER_DAYS} days.")
    elif should:
        reason = (f"{prod['name']} has {stock} units (~{cover:.1f} days at "
                  f"{rate:.1f}/day), enough to outlast the {lead}-day supplier "
                  f"lead time but below the reorder point of "
                  f"{reorder_point:.0f} (lead time + weekly review + safety "
                  f"stock). Order {qty} now to avoid running short.")
    else:
        reason = (f"{prod['name']} has {stock} units (~{cover:.0f} days of "
                  f"cover at {rate:.1f}/day), above the reorder point of "
                  f"{reorder_point:.0f}. No order needed yet.")
    if confidence == "low":
        reason += (f" Only {history_days} days of history, so treat this as a "
                   f"rough estimate.")

    return Recommendation(
        sku=sku, as_of=str(as_of.date()), stock_on_hand=stock,
        daily_demand=round(rate, 3), demand_std=round(std, 3),
        lead_time_days=lead, reorder_point=round(reorder_point, 1),
        days_of_cover=None if cover is None else round(cover, 1),
        should_reorder=bool(should), recommended_qty=qty, urgency=urgency,
        confidence=confidence, reason=reason,
    )


def recommend_all(as_of, products: pd.DataFrame, txns: pd.DataFrame):
    return [recommend(s, as_of, products, txns) for s in products.sku]


def backtest(products: pd.DataFrame, txns: pd.DataFrame, horizon: int = 30):
    """Forecast `horizon` days of demand from the train cutoff; score vs holdout.

    Compares the engine's rate to a naive all-history mean baseline.
    """
    holdout = txns[txns.split == "holdout"]
    cutoff = txns[txns.split == "train"].date.max()
    end = cutoff + pd.Timedelta(days=horizon)
    rows = []
    for sku in products.sku:
        rec = recommend(sku, cutoff, products, txns)
        actual = holdout[(holdout.sku == sku) & (holdout.type == "SALE")
                         & (holdout.date <= end)]["quantity"].sum()
        hist = daily_sales(sku, cutoff, txns)
        naive = float(hist.mean()) if len(hist) else 0.0
        rows.append({
            "sku": sku,
            "persona": products.loc[products.sku == sku, "persona"].iloc[0],
            "actual": float(actual),
            "engine": rec.daily_demand * horizon,
            "naive": naive * horizon,
        })
    df = pd.DataFrame(rows)
    out = {}
    for name in ("engine", "naive"):
        out[name] = {
            "MAE": float((df[name] - df.actual).abs().mean()),
            "WAPE": float((df[name] - df.actual).abs().sum() / max(df.actual.sum(), 1e-9)),
        }
    return df, out, cutoff


if __name__ == "__main__":
    import sys
    d = sys.argv[1] if len(sys.argv) > 1 else "dataset/output"
    products, txns = load_data(d)
    df, scores, cutoff = backtest(products, txns)
    print(f"Backtest from {cutoff.date()} (30-day demand per SKU)")
    print(df.round(1).to_string(index=False))
    print(scores)
