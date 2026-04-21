"""API #10 — Cook County Treasurer (Tier 3 pipeline, free).

Tax payment status per PIN — joined to Assessor to flag delinquent buildings.
Source: cookcountytreasurer.com bulk downloads (no key).
"""

from pathlib import Path

import pandas as pd
import requests

BULK_URL = "https://www.cookcountytreasurer.com/<tax-status-export>.csv"
RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"


def download(dest: Path = RAW_DIR / "treasurer.csv") -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    # TODO: confirm exact Treasurer export URL; the site does not publish a
    # stable API — may require scraping or partnership data feed.
    with requests.get(BULK_URL, stream=True, timeout=300) as r:
        r.raise_for_status()
        with dest.open("wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
    return dest


def load(csv_path: Path = RAW_DIR / "treasurer.csv") -> pd.DataFrame:
    return pd.read_csv(csv_path, dtype={"pin": str})


if __name__ == "__main__":
    download()
