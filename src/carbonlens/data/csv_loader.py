from io import BytesIO

import pandas as pd


def load_csv(file_bytes: bytes) -> pd.DataFrame:
    """Load CSV bytes; validate schema separately."""
    return pd.read_csv(BytesIO(file_bytes), nrows=50_001)
