"""One-shot CTA loader using Supabase REST API directly.

Bypasses supabase-py to dodge the Python 3.9 + gotrue/httpx/websockets/
pyiceberg dep cascade that breaks the orchestrator path. Replicates the
silver row shape from scripts/transformers/cta.py.

TEMPORARY: delete this file once the orchestrator works end-to-end on a
modern Python (3.11+) where supabase-py installs cleanly.

Run:
    python scripts/seed_cta_oneshot.py
"""
import io
import os
import zipfile
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

URL = os.environ["SUPABASE_URL"]
KEY = os.environ["SUPABASE_SERVICE_KEY"]
GTFS = "https://www.transitchicago.com/downloads/sch_data/google_transit.zip"
N, S, E, W = 42.023, 41.644, -87.524, -87.940  # Chicago bbox

print("Downloading GTFS feed...")
r = requests.get(GTFS, timeout=120)
r.raise_for_status()
with zipfile.ZipFile(io.BytesIO(r.content)) as z:
    df = pd.read_csv(z.open("stops.txt"))
print(f"  raw rows: {len(df)}")

df = df[(df.stop_lat >= S) & (df.stop_lat <= N) &
        (df.stop_lon >= W) & (df.stop_lon <= E)]
silver = []
seen = set()
for _, row in df.iterrows():
    sid = int(row.stop_id)
    if sid in seen:
        continue
    seen.add(sid)
    silver.append({
        "id": sid,
        "name": row.stop_name,
        "lines": [],
        "accessible": int(row.get("wheelchair_boarding", 0) or 0) == 1,
        "location": f"SRID=4326;POINT({row.stop_lon} {row.stop_lat})",
    })
print(f"  filtered + deduped: {len(silver)} Chicago stops")

headers = {
    "apikey": KEY,
    "Authorization": f"Bearer {KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates",
}
endpoint = f"{URL}/rest/v1/cta_stops"

total = 0
for i in range(0, len(silver), 500):
    batch = silver[i:i + 500]
    resp = requests.post(endpoint, headers=headers, json=batch, timeout=60)
    if not resp.ok:
        print(f"FAIL batch starting at {i}: {resp.status_code}\n{resp.text[:400]}")
        raise SystemExit(1)
    total += len(batch)
    print(f"  upserted {total}/{len(silver)}")

print(f"Done. {total} CTA stops loaded into cta_stops.")
