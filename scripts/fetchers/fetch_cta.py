"""API #9 — CTA GTFS feed (Tier 3 pipeline, free, no key).

Source: transitchicago.com/developers/gtfs.aspx — ZIP download.
Only stops.txt is needed for proximity queries; store lat/lng + lines.
"""

import io
import sys
import zipfile
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.bronze_store import write_bronze

GTFS_URL = "https://www.transitchicago.com/downloads/sch_data/google_transit.zip"
RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"

# Chicago bounding box — drops suburban stops that GTFS sometimes includes.
CHI_NORTH, CHI_SOUTH = 42.023, 41.644
CHI_EAST, CHI_WEST = -87.524, -87.940


def fetch_stops() -> pd.DataFrame:
    res = requests.get(GTFS_URL, timeout=120)
    res.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(res.content)) as zf:
        with zf.open("stops.txt") as f:
            return pd.read_csv(f)


def run(run_id: str) -> list[dict]:
    """Orchestrator entrypoint: fetch → bronze → silver-shaped rows."""
    raw = fetch_stops()

    # Filter to Chicago bounds (GTFS sometimes includes Oak Park, Evanston, etc.)
    in_chicago = (
        raw["stop_lat"].between(CHI_SOUTH, CHI_NORTH)
        & raw["stop_lon"].between(CHI_WEST, CHI_EAST)
    )
    raw = raw[in_chicago].reset_index(drop=True)

    # Bronze: store raw as-is for replay / audit
    raw_rows = raw.to_dict(orient="records")
    write_bronze("cta", run_id, raw_rows)

    # Silver: shape rows to match cta_stops schema
    # NOTE: `lines` requires joining stop_times + trips + routes — deferred.
    silver = [
        {
            "id": idx + 1,
            "name": r["stop_name"],
            "lines": [],
            "accessible": bool(r.get("wheelchair_boarding") == 1),
            "location": f"SRID=4326;POINT({r['stop_lon']} {r['stop_lat']})",
        }
        for idx, r in enumerate(raw_rows)
    ]
    return silver


if __name__ == "__main__":
    df = fetch_stops()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(RAW_DIR / "cta_stops.csv", index=False)
    print(f"cta: {len(df)} stops saved")
