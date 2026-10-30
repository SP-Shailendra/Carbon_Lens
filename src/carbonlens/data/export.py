import json
from typing import Any

import pandas as pd


def report_csv(report: dict[str, Any]) -> str:
    frame = pd.DataFrame(report["rows"])
    for column in ("factor", "provenance", "assumptions"):
        if column in frame:
            frame[column] = frame[column].map(lambda value: json.dumps(value, ensure_ascii=True))
    for column in frame.select_dtypes(include="object").columns:
        frame[column] = frame[column].map(
            lambda value: (
                "'" + value
                if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r"))
                else value
            )
        )
    return frame.to_csv(index=False)
