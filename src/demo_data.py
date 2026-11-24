"""Small deterministic inputs to demonstrate known measurement outcomes."""

import pandas as pd

from .orderbook.builder import BAR_INTERVAL_US, LEVELS


def make_demo_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Generate events and expected snapshots directly from a price/size schedule."""
    events = []
    reference = []
    start = 1_700_000_000_000_000
    n_bars = 12
    previous_best = None

    for bar in range(n_bars):
        ts = start + bar * BAR_INTERVAL_US
        best_bid = 100 + bar + (bar % 3)
        best_ask = 150 - bar
        # Fixed levels are behind the moving best quote on each side.
        bids = [(best_bid, float(2 + bar % 4))] + [(99 - i, 4.0) for i in range(LEVELS - 1)]
        asks = [(best_ask, float(3 + bar % 5))] + [(151 + i, 5.0) for i in range(LEVELS - 1)]

        def add_event(side: str, price: int, amount: float) -> None:
            events.append((ts, bar == 0, side, price, amount))

        if previous_best:
            add_event("bid", previous_best[0], 0)
            add_event("ask", previous_best[1], 0)
        for side, levels in (("bid", bids), ("ask", asks)):
            for price, amount in (levels if bar == 0 else levels[:1]):
                add_event(side, price, amount)

        expected = {"timestamp": ts + 9_000_000}
        for side, levels in (("bid", bids), ("ask", asks)):
            for i, (price, amount) in enumerate(levels):
                expected[f"{side}s[{i}].price"] = price
                expected[f"{side}s[{i}].amount"] = amount
        if bar == 4:
            expected["bids[0].amount"] += 2.0  # Known discrepancy injected into one input.
        reference.append(expected)
        previous_best = best_bid, best_ask

    # Marks that replay has reached the end of bar 11; not part of a closed bar.
    events.append((start + n_bars * BAR_INTERVAL_US, False, "ask", 151, 5.0))
    return (
        pd.DataFrame(events, columns=["timestamp", "is_snapshot", "side", "price", "amount"]),
        pd.DataFrame(reference),
    )
