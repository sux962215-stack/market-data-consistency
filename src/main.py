"""Run the offline order book comparison using synthetic or local inputs."""

import argparse
from pathlib import Path

import pandas as pd

from .attribution.ic_analysis import compare_dataframes
from .demo_data import make_demo_data
from .orderbook.builder import aggregate_reference, reconstruct_order_book


def run(events: pd.DataFrame, snapshots: pd.DataFrame, out: Path, *, synthetic: bool) -> pd.DataFrame:
    reconstructed = reconstruct_order_book(events)
    reference = aggregate_reference(snapshots)
    metrics = compare_dataframes(reconstructed, reference)

    out.mkdir(parents=True, exist_ok=True)
    reconstructed.to_csv(out / "reconstructed.csv", index=False)
    reference.to_csv(out / "reference.csv", index=False)
    metrics.to_csv(out / "per_feature_metrics.csv", index=False)

    shared = len(set(reconstructed["bar_start"]) & set(reference["bar_start"]))
    input_label = "synthetic, not a market benchmark" if synthetic else "local files (unverified provenance)"
    report = [
        "# Order book consistency report",
        "",
        f"Input: {input_label}.",
        f"Windows: {len(reconstructed)} reconstructed, {len(reference)} reference, {shared} shared.",
        "",
        "| Feature | Paired samples | Pearson IC | MAE | RMSE |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for r in metrics[metrics["feature"].isin(["bid_0_price", "bid_0_amount", "ask_0_price", "ask_0_amount"])].itertuples():
        stats = ["—" if pd.isna(value) else f"{value:.6f}" for value in (r.ic, r.mae, r.rmse)]
        report.append(f"| {r.feature} | {r.n_valid} | {' | '.join(stats)} |")
    report += ["", "All levels: [per_feature_metrics.csv](per_feature_metrics.csv).", ""]
    if synthetic:
        report.append("Attribution: a quantity difference of +2 was injected into one reference best bid; prices were unchanged.")
    else:
        report.append("Differences identify where to investigate, not why they occurred. Check coverage, sampling and feed semantics.")
    (out / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--incremental", type=Path, help="local incremental L2 CSV")
    parser.add_argument("--reference", type=Path, help="local reference snapshot CSV")
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    args = parser.parse_args()
    if (args.incremental is None) != (args.reference is None):
        parser.error("--incremental and --reference must be supplied together")

    synthetic = args.incremental is None
    if synthetic:
        events, snapshots = make_demo_data()
    else:
        events, snapshots = pd.read_csv(args.incremental), pd.read_csv(args.reference)
    run(events, snapshots, args.output_dir, synthetic=synthetic)
    print(f"Report: {args.output_dir / 'report.md'}")


if __name__ == "__main__":
    main()
