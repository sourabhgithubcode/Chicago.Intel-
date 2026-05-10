"""API #8 — Cook County Assessor (Tier 3 pipeline).

Source: Cook County Open Data Socrata at datacatalog.cookcountyil.gov.
Four PIN-keyed datasets joined in Python — see transformers/assessor.py
for the silver schema mapping.

INGEST_YEAR pins all four datasets to a single tax year (latest fully-
populated). Sales are not year-filtered — we want the most recent real
sale across history, with $10K floor + class restriction to drop family
quitclaim transfers and split-out tax-only deeds.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Iterable

from sodapy import Socrata

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from transformers.assessor import to_silver
from utils.bronze_store import write_bronze

DOMAIN = "datacatalog.cookcountyil.gov"
TOKEN = os.getenv("COOK_COUNTY_TOKEN")  # optional; throttled if absent

INGEST_YEAR = 2024
PAGE_SIZE = 50_000

UNIVERSE = "nj4t-kc8j"
ADDRESSES = "3723-97qp"
CHARACTERISTICS = "x54s-btds"
SALES = "wvhk-k5uv"

SALE_FLOOR = 10_000
SALE_YEAR_FLOOR = 2010


def _paginate(client: Socrata, dataset: str, where: str, select: str) -> list[dict]:
    """Page a Socrata dataset under `where` until exhausted."""
    rows: list[dict] = []
    offset = 0
    while True:
        chunk = client.get(dataset, select=select, where=where,
                           limit=PAGE_SIZE, offset=offset)
        if not chunk:
            break
        rows.extend(chunk)
        if len(chunk) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return rows


def fetch_all() -> dict[str, list[dict]]:
    """Fetch the 4 bronze streams. Caller writes bronze + transforms."""
    client = Socrata(DOMAIN, TOKEN, timeout=120)

    universe = _paginate(
        client, UNIVERSE,
        where=f"year={INGEST_YEAR} AND cook_municipality_name='CITY OF CHICAGO' "
              f"AND lat IS NOT NULL AND lon IS NOT NULL",
        select="pin,lat,lon,school_elementary_district_name",
    )

    addresses = _paginate(
        client, ADDRESSES,
        where=f"year={INGEST_YEAR} AND prop_address_state='IL' "
              f"AND prop_address_city_name='CHICAGO'",
        select="pin,prop_address_full,owner_address_name",
    )

    characteristics = _paginate(
        client, CHARACTERISTICS,
        where=f"year={INGEST_YEAR} AND char_yrblt > 0",
        select="pin,char_yrblt",
    )

    sales = _paginate(
        client, SALES,
        where=f"year >= {SALE_YEAR_FLOOR} AND sale_price > {SALE_FLOOR}",
        select="pin,sale_date,sale_price",
    )

    return {
        "universe": universe,
        "addresses": addresses,
        "characteristics": characteristics,
        "sales": sales,
    }


def run(run_id: str) -> list[dict]:
    bronze = fetch_all()
    for stream, rows in bronze.items():
        write_bronze(f"assessor.{stream}", run_id, rows)
    return to_silver(
        universe=bronze["universe"],
        addresses=bronze["addresses"],
        characteristics=bronze["characteristics"],
        sales=bronze["sales"],
    )


if __name__ == "__main__":
    out = fetch_all()
    for k, v in out.items():
        print(f"assessor.{k}: {len(v)} rows")
