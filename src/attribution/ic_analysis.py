"""Compare aligned price and amount features without filling missing data."""

import numpy as np
import pandas as pd


def compare_dataframes(reconstructed: pd.DataFrame, reference: pd.DataFrame) -> pd.DataFrame:
    """Compute Pearson correlation (IC), errors and overlap per feature."""
    common = [col for col in reconstructed if col != "bar_start" and col in reference]
    left = reconstructed.set_index("bar_start")
    right = reference.set_index("bar_start")
    if not left.index.is_unique or not right.index.is_unique:
        raise ValueError("expected at most one snapshot per window on each side")
    shared_windows = len(left.index.intersection(right.index))
    win_union = left.index.union(right.index)
    result = []
    for feature in common:
        a = pd.to_numeric(left[feature], errors="raise").reindex(win_union)
        b = pd.to_numeric(right[feature], errors="raise").reindex(win_union)
        valid = np.isfinite(a) & np.isfinite(b)
        x, y = a[valid], b[valid]
        error = x - y
        result.append({
            "feature": feature,
            "n_valid": len(error),
            "n_reconstructed_windows": len(left),
            "n_reference_windows": len(right),
            "n_shared_windows": shared_windows,
            "ic": x.corr(y) if len(error) >= 3 and x.nunique() > 1 and y.nunique() > 1 else np.nan,
            "mae": error.abs().mean(),
            "rmse": np.sqrt(error.pow(2).mean()),
        })
    return pd.DataFrame(result)
