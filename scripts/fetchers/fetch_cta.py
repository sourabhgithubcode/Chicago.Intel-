"""API #9 — CTA GTFS feed (Tier 3 pipeline, free, no key).

Source: transitchicago.com/developers/gtfs.aspx — ZIP download.
Only stops.txt is needed for proximity queries; store lat/lng + lines.

TODO: backfill `lines` by joining stop_times → trips → routes (deferred —
needs three more GTFS files and a small in-memory join).
"""

import io
import sys
import zipfile
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from transformers.cta import to_silver
from utils.bronze_store import write_bronze

GTFS_URL = "https://www.transitchicago.com/downloads/sch_data/google_transit.zip"
RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"


def fetch_stops() -> pd.DataFrame:
    res = requests.get(GTFS_URL, timeout=120)
    res.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(res.content)) as zf:
        with zf.open("stops.txt") as f:
            return pd.read_csv(f)


def run(run_id: str) -> list[dict]:
    """Orchestrator entrypoint: fetch → bronze → silver-shaped rows."""
    raw_df = fetch_stops()

    # Replace pandas NaN with None so JSON serialization doesn't emit
    # the bare token `NaN` (which is invalid JSON and breaks bronze replay).
    raw_rows = raw_df.where(raw_df.notna(), None).to_dict(orient="records")

    write_bronze("cta", run_id, raw_rows)
    return to_silver(raw_rows)


if __name__ == "__main__":
    df = fetch_stops()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(RAW_DIR / "cta_stops.csv", index=False)
    print(f"cta: {len(df)} stops saved")
