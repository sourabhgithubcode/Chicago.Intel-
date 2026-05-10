"""Cook County Assessor — bronze rows from 4 datasets → silver buildings rows.

Sources (datacatalog.cookcountyil.gov, all PIN-keyed, all multi-year):
  - Parcel Universe (nj4t-kc8j): pin, lat/lon, school district, Chicago filter
  - Parcel Addresses (3723-97qp): prop_address_full, owner_address_name
  - Improvement Characteristics (x54s-btds): char_yrblt (single/multi-fam only)
  - Parcel Sales (wvhk-k5uv): latest arms-length sale per PIN

Confidence: 9/10 — Cook County Assessor is authoritative for parcel facts.

Silver schema (migration 001) — populated columns only; the rest are filled
by other jobs (311 reconcile, treasurer, FEMA live, address normalization):
    buildings(pin TEXT PK, address TEXT NOT NULL, owner TEXT,
              year_built INT, purchase_year INT, purchase_price BIGINT,
              school_elem TEXT, location GEOMETRY(POINT, 4326))

`owner` here is the *taxpayer's* mailing name (owner_address_name), the
only owner-like field Cook County exposes — beneficial owner is not public.
"""
from __future__ import annotations

from typing import Iterable


def to_silver(
    universe: Iterable[dict],
    addresses: Iterable[dict],
    characteristics: Iterable[dict],
    sales: Iterable[dict],
) -> list[dict]:
    # Index addresses + characteristics by PIN — one row per PIN per year,
    # universe is already filtered to year=2024 so these can be dict-keyed.
    addr_by_pin = {r["pin"]: r for r in addresses if r.get("pin")}
    char_by_pin = {r["pin"]: r for r in characteristics if r.get("pin")}

    # Latest qualifying sale per PIN: walk sales once, keep the row with the
    # most recent sale_date. Sales are not filtered to 2024 — we want the
    # most recent real sale across all history.
    latest_sale: dict[str, dict] = {}
    for r in sales:
        pin = r.get("pin")
        sd = r.get("sale_date")
        if not pin or not sd:
            continue
        prev = latest_sale.get(pin)
        if prev is None or sd > prev["sale_date"]:
            latest_sale[pin] = r

    silver = []
    seen = set()
    for u in universe:
        pin = u.get("pin")
        if not pin or pin in seen:
            continue
        try:
            lat = float(u["lat"])
            lng = float(u["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        addr_row = addr_by_pin.get(pin)
        if not addr_row:
            continue  # buildings.address is NOT NULL — skip if no address
        address = addr_row.get("prop_address_full")
        if not address:
            continue
        seen.add(pin)

        char_row = char_by_pin.get(pin) or {}
        sale_row = latest_sale.get(pin) or {}

        try:
            year_built = int(float(char_row["char_yrblt"])) if char_row.get("char_yrblt") else None
        except (TypeError, ValueError):
            year_built = None

        purchase_year = None
        purchase_price = None
        if sale_row.get("sale_date"):
            purchase_year = int(sale_row["sale_date"][:4])
            try:
                purchase_price = int(float(sale_row["sale_price"]))
            except (TypeError, ValueError):
                purchase_price = None

        silver.append({
            "pin": pin,
            "address": address,
            "address_norm": " ".join(address.upper().split()),
            "owner": addr_row.get("owner_address_name"),
            "year_built": year_built,
            "purchase_year": purchase_year,
            "purchase_price": purchase_price,
            "school_elem": u.get("school_elementary_district_name"),
            "location": f"SRID=4326;POINT({lng} {lat})",
        })
    return silver
