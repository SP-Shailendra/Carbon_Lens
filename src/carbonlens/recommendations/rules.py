import pandas as pd


def select_top_hotspots(frame: pd.DataFrame, score_column: str, limit: int = 3) -> pd.DataFrame:
    """Select rows by a precomputed numeric score; does not calculate emissions."""
    if score_column not in frame.columns:
        raise ValueError(f"Missing score column: {score_column}")
    if limit < 1:
        raise ValueError("limit must be at least 1")
    return frame.sort_values(score_column, ascending=False).head(limit).copy()
