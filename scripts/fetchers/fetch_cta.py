"""API #9 — CTA GTFS feed (Tier 3 pipeline, free, no key).

Source: transitchicago.com/developers/gtfs.aspx — ZIP download.
Only stops.txt is needed for proximity queries; store lat/lng + lines.
"""

import io
import zipfile
from pathlib import Path

import pandas as pd
import requests

GTFS_URL = "https://www.transitchicago.com/downloads/sch_data/google_transit.zip"
RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"


def fetch_stops() -> pd.DataFrame:
    res = requests.get(GTFS_URL, timeout=120)
    res.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(res.content)) as zf:
        with zf.open("stops.txt") as f:
            return pd.read_csv(f)


if __name__ == "__main__":
    df = fetch_stops()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(RAW_DIR / "cta_stops.csv", index=False)
    print(f"cta: {len(df)} stops saved")
