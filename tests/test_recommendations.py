import pandas as pd
import pytest

from carbonlens.recommendations.rules import select_top_hotspots


def test_selects_top_three():
    frame = pd.DataFrame({"service": ["a", "b", "c", "d"], "score": [1, 5, 3, 2]})
    result = select_top_hotspots(frame, "score", limit=3)
    assert result["service"].tolist() == ["b", "c", "d"]


def test_missing_score_column_raises():
    with pytest.raises(ValueError):
        select_top_hotspots(pd.DataFrame({"service": ["a"]}), "score")
