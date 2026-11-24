"""Replay normalized incremental L2 rows into causal 10-second book snapshots."""

from itertools import groupby

import numpy as np
import pandas as pd


BAR_INTERVAL_US = 10_000_000
LEVELS = 25
SIDE_FIELDS = ("price", "amount")


def snapshot_fields() -> dict[str, str]:
    """Map Tardis-style snapshot columns to the demo's output columns."""
    return {
        f"{side}s[{level}].{field}": f"{side}_{level}_{field}"
        for level in range(LEVELS)
        for side in ("bid", "ask")
        for field in SIDE_FIELDS
    }


def to_timestamp_us(series: pd.Series) -> pd.Series:
    """Require nonnegative integer timestamps in microseconds."""
    values = pd.to_numeric(series, errors="raise")
    # Stay within the exact integer range even for CSV columns parsed as floats.
    if not (values.between(0, 2**53 - 1) & (values % 1 == 0)).fillna(False).all():
        raise ValueError("timestamp must contain nonnegative integer microseconds")
    return values.astype("int64")


class OrderBook:
    """Store absolute quantities; retain deep levels even if not exported."""

    def __init__(self):
        self.bids: dict[float, float] = {}
        self.asks: dict[float, float] = {}

    def apply(self, side: str, price: float, amount: float) -> None:
        book = self.bids if side == "bid" else self.asks
        if amount == 0:
            book.pop(price, None)
        else:
            book[price] = amount

    def is_ready(self) -> bool:
        return bool(self.bids and self.asks)

    def snapshot(self, bar_start: int) -> dict:
        row = {"bar_start": bar_start}
        for side, book in (("bid", self.bids), ("ask", self.asks)):
            levels = sorted(book.items(), reverse=(side == "bid"))[:LEVELS]
            for i, (price, amount) in enumerate(levels):
                row[f"{side}_{i}_price"] = price
                row[f"{side}_{i}_amount"] = amount
        return row


def reconstruct_order_book(events: pd.DataFrame) -> pd.DataFrame:
    """Return the state strictly before each closed window's right edge.

    Input must be in nondecreasing event-time order. Equal-time rows retain
    source order; contiguous snapshot rows with the same timestamp form a
    single reset. No incomplete trailing window is emitted.
    """
    required = ["timestamp", "is_snapshot", "side", "price", "amount"]
    missing = set(required).difference(events.columns)
    if missing:
        raise ValueError(f"incremental data is missing: {', '.join(sorted(missing))}")
    columns = ["bar_start", *snapshot_fields().values()]
    if events.empty:
        return pd.DataFrame(columns=columns)

    ts = to_timestamp_us(events["timestamp"])
    if not ts.is_monotonic_increasing:
        raise ValueError("incremental timestamps must be nondecreasing")
    flags = events["is_snapshot"].astype(str).str.strip().str.lower()
    if not flags.isin(["true", "false"]).all():
        raise ValueError("is_snapshot must contain true/false values")
    if not events["side"].isin(["bid", "ask"]).all():
        raise ValueError("side must be bid or ask")
    prices = pd.to_numeric(events["price"], errors="raise").to_numpy(dtype=float)
    amounts = pd.to_numeric(events["amount"], errors="raise").to_numpy(dtype=float)
    if not (np.isfinite(prices) & (prices > 0)).all():
        raise ValueError("price must be finite and positive")
    if not (np.isfinite(amounts) & (amounts >= 0)).all():
        raise ValueError("amount must be finite and nonnegative")

    rows = zip(ts, flags == "true", events["side"], prices, amounts)
    next_close = (int(ts.iloc[0]) // BAR_INTERVAL_US + 1) * BAR_INTERVAL_US
    book = OrderBook()
    initialized = False
    output = []
    for (timestamp, is_snapshot), batch in groupby(rows, key=lambda row: row[:2]):
        # Emit before applying events at, or after, the window's right edge.
        if not book.is_ready() and timestamp >= next_close:
            next_close = (timestamp // BAR_INTERVAL_US + 1) * BAR_INTERVAL_US
        while next_close <= timestamp:
            output.append(book.snapshot(next_close - BAR_INTERVAL_US))
            next_close += BAR_INTERVAL_US

        if is_snapshot:
            book = OrderBook()
            initialized = True
        if initialized:
            for _, _, side, price, amount in batch:
                book.apply(side, price, amount)

    return pd.DataFrame(output, columns=columns)


def aggregate_reference(snapshots: pd.DataFrame) -> pd.DataFrame:
    """Take the last entire reference snapshot in each half-open window."""
    fields = snapshot_fields()
    if "timestamp" not in snapshots or not (set(fields) & set(snapshots)):
        raise ValueError("reference needs timestamp and Tardis-style level columns")
    timestamp = to_timestamp_us(snapshots["timestamp"])
    bar_start = (timestamp // BAR_INTERVAL_US * BAR_INTERVAL_US).rename("bar_start")
    levels = snapshots.reindex(columns=list(fields)).rename(columns=fields)
    df = pd.concat([bar_start, timestamp, levels], axis=1)
    df = df.sort_values("timestamp", kind="stable").groupby("bar_start", sort=False).tail(1)
    return df.drop(columns="timestamp").reset_index(drop=True)
