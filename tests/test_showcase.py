import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.attribution.ic_analysis import compare_dataframes
from src.demo_data import make_demo_data
from src.main import run
from src.orderbook.builder import BAR_INTERVAL_US, aggregate_reference, reconstruct_order_book


W = BAR_INTERVAL_US
EVENT_COLUMNS = ["timestamp", "is_snapshot", "side", "price", "amount"]


def events(rows):
    return pd.DataFrame(rows, columns=EVENT_COLUMNS)


class ReplayTests(unittest.TestCase):
    def test_boundary_and_empty_window_use_only_past_events(self):
        # No event at the first close; the 10s-20s window should not see the 20s update either.
        actual = reconstruct_order_book(events([
            (1, True, "bid", 100, 1),
            (1, True, "ask", 105, 3),
            (2 * W, False, "bid", 101, 5),
            (3 * W, False, "bid", 102, 6),
        ]))
        self.assertEqual(actual["bar_start"].tolist(), [0, W, 2 * W])
        self.assertEqual(actual["bid_0_price"].tolist(), [100, 100, 101])

    def test_snapshot_reset_deletion_and_equal_time_row_order(self):
        actual = reconstruct_order_book(events([
            (0, False, "bid", 200, 10),  # pre-snapshot update ignored
            (1, True, "bid", 100, 1),
            (1, True, "ask", 105, 3),
            (2, False, "bid", 100.00001, 4),
            (2, False, "bid", 100.00002, 3),
            (2, False, "bid", 100.00002, 0),
            (W, True, "bid", 98, 6),
            (W, True, "ask", 108, 7),
            (W, False, "bid", 98, 8),
            (2 * W, False, "bid", 98, 8),
        ]))
        self.assertEqual(actual["bid_0_price"].tolist(), [100.00001, 98])
        self.assertEqual(actual["bid_0_amount"].tolist(), [4, 8])
        self.assertTrue(pd.isna(actual.loc[1, "bid_1_price"]))

    def test_pre_initialization_window_is_not_emitted(self):
        actual = reconstruct_order_book(events([
            (0, False, "bid", 100, 1),
            (W, True, "bid", 100, 1),
            (W, True, "ask", 105, 3),
            (2 * W, False, "bid", 100, 2),
        ]))
        self.assertEqual(actual["bar_start"].tolist(), [W])

    def test_unsorted_events_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "nondecreasing"):
            reconstruct_order_book(events([(2, True, "bid", 100, 1), (1, True, "ask", 105, 3)]))


class ComparisonTests(unittest.TestCase):
    def test_reference_does_not_merge_depth_across_snapshots(self):
        actual = aggregate_reference(pd.DataFrame({
            "timestamp": [1, 2, W], "bids[0].price": [10.0, 11.0, 12.0],
            "bids[1].price": [9.0, None, 9.0],
        }))
        self.assertEqual(actual["bid_0_price"].tolist(), [11.0, 12.0])
        self.assertTrue(pd.isna(actual.loc[0, "bid_1_price"]))

    def test_no_correlation_for_constant_or_insufficient_pairs(self):
        left = pd.DataFrame({"bar_start": [0, W, 2 * W], "varying": [1, 2, 3], "constant": [4, 4, 4]})
        right = pd.DataFrame({"bar_start": [W, 2 * W, 3 * W], "varying": [2, 3, 4], "constant": [4, 4, 4]})
        result = compare_dataframes(left, right).set_index("feature")
        self.assertEqual(result.loc["varying", "n_valid"], 2)
        self.assertEqual(result.loc["constant", "n_shared_windows"], 2)
        self.assertTrue(result["ic"].isna().all())
        self.assertEqual(result.loc["varying", "mae"], 0)
        self.assertTrue(pd.isna(compare_dataframes(left, left).set_index("feature").loc["constant", "ic"]))

    def test_duplicate_windows_do_not_create_extra_pairs(self):
        left = pd.DataFrame({"bar_start": [0, 0], "bid_0_price": [100, 101]})
        right = pd.DataFrame({"bar_start": [0], "bid_0_price": [100]})
        with self.assertRaisesRegex(ValueError, "one snapshot per window"):
            compare_dataframes(left, right)

    def test_known_demo_discrepancy_and_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            result = run(*make_demo_data(), out, synthetic=True).set_index("feature")
            self.assertEqual(len(result), 100)
            self.assertEqual(result.loc["bid_0_amount", "n_valid"], 12)
            self.assertAlmostEqual(result.loc["bid_0_amount", "mae"], 2 / 12)
            self.assertAlmostEqual(result.loc["bid_0_amount", "rmse"], 2 / 12**0.5)
            unaffected = result.drop(index="bid_0_amount")
            self.assertTrue((unaffected["mae"] == 0).all())
            self.assertAlmostEqual(result.loc["bid_0_price", "ic"], 1.0)
            self.assertIn("synthetic, not a market benchmark", (out / "report.md").read_text(encoding="utf-8"))

    def test_cli_reads_local_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            left = folder / "incremental.csv"
            right = folder / "snapshots.csv"
            out = folder / "report"
            feed, snapshot = make_demo_data()
            feed.to_csv(left, index=False)
            snapshot.to_csv(right, index=False)
            result = subprocess.run([
                sys.executable, "-W", "error", "-m", "src.main",
                "--incremental", str(left), "--reference", str(right), "--output-dir", str(out),
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = (out / "report.md").read_text(encoding="utf-8")
            self.assertIn("12 shared", report)
            self.assertIn("local files", report)


if __name__ == "__main__":
    unittest.main()
