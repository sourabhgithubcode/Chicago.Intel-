"""Chicago Street Centerlines (Tier 3 pipeline, free, no key required).

Source: Chicago Data Portal Socrata 6imu-meau.
Confidence: 9/10 — official city centerline data.

~50K segments. Refresh annually (rarely changes). Bronze + silver shaping;
spatial assignment to ccas/tracts and FK back from buildings happens in the
reconcile step (see DATA_DICTIONARY §10.3).
"""

import os
import sys
from pathlib import Path

from sodapy import Socrata

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from transformers.streets import to_silver
from utils.bronze_store import write_bronze

DOMAIN = "data.cityofchicago.org"
DATASET = "6imu-meau"
TOKEN = os.getenv("CHICAGO_DATA_TOKEN")

PAGE_SIZE = 10_000  # Socrata default cap per request


def fetch_all() -> list[dict]:
    """Page through the centerlines dataset until exhausted."""
    client = Socrata(DOMAIN, TOKEN)
    rows: list[dict] = []
    offset = 0
    while True:
        chunk = client.get(DATASET, limit=PAGE_SIZE, offset=offset)
        if not chunk:
            break
        rows.extend(chunk)
        if len(chunk) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return rows


def run(run_id: str) -> list[dict]:
    """Orchestrator entrypoint: fetch → bronze → silver-shaped rows."""
    raw = fetch_all()
    write_bronze("streets", run_id, raw)
    return to_silver(raw)


if __name__ == "__main__":
    rows = fetch_all()
    print(f"streets: {len(rows)} centerline segments fetched")
