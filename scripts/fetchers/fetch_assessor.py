"""API #8 — Cook County Assessor (Tier 3 pipeline, free bulk CSV).

Source: datacatalog.cookcountyil.gov — no key required.
Data: owner, purchase price, year built, tax status per parcel.
Refresh: quarterly ZIP download.
"""

from pathlib import Path

import pandas as pd
import requests

BULK_URL = "https://datacatalog.cookcountyil.gov/resource/<assessor-dataset>.csv"
RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"


def download_csv(dest: Path = RAW_DIR / "assessor.csv") -> Path:
    """Stream the Assessor bulk CSV to disk. Caller joins with Treasurer tax status."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    # TODO: pin the exact Cook County resource ID once confirmed.
    with requests.get(BULK_URL, stream=True, timeout=300) as r:
        r.raise_for_status()
        with dest.open("wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
    return dest


def load(csv_path: Path = RAW_DIR / "assessor.csv") -> pd.DataFrame:
    return pd.read_csv(csv_path, dtype={"pin": str})


if __name__ == "__main__":
    download_csv()
