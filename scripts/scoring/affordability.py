"""Affordability score (0–10) per CCA — modeled Housing + Transportation cost
as a share of income.

OUR ESTIMATE, not HUD's published Location Affordability Index. We borrow the
LAI *structure* (H+T ÷ income) but recompute on current 2019–23 ACS. The
transportation half is a transparent, simplified model — NOT HUD's simultaneous-
equations model — so it must always be labeled as our estimate.

    housing_mo    = ACS median gross rent (already on ccas.rent_median; includes
                    utilities if paid by renter — ACS B25064)
    transport_mo  = transit_share × CTA_PASS                  (transit commuters' pass cost)
                  + autos_per_hh × PER_AUTO_ANNUAL / 12        (auto ownership/operating)
    ht_ratio      = (housing_mo + transport_mo) × 12 ÷ REFERENCE_INCOME
    afford_score  = clamp(10 × (HI − ht_ratio) / (HI − LO), 0, 10)
                    LO 30% ⇒ 10, HUD 45% benchmark ⇒ 5, HI 60% ⇒ 0

We divide by ONE fixed reference income (not each area's own median): "how
affordable is this area to a typical Chicago earner". Dividing by the area's own
median (true HUD LAI) perversely ranks wealthy high-rent areas as most affordable.
REFERENCE_INCOME is the placeholder the user-salary input will replace live.

Cost parameters (sourced, tunable — do not silently change):
  CTA_PASS         $75   CTA 30-day pass, 2025 (rises to $85 on 2026-02-01).
                         https://www.transitchicago.com/passes/
  PER_AUTO_ANNUAL  $12,297  AAA 2024 'Your Driving Costs' new-vehicle full
                         ownership (75k mi / 5 yr). UPPER BOUND — most households
                         own older, cheaper cars; tune down if calibrating.
                         https://newsroom.aaa.com/2024/09/

Caveat ("what this does not tell you"): transit cost assumes commuters buy 30-day
passes; auto cost uses AAA's new-vehicle figure; neither reflects an individual's
actual car or rent. Confidence 6/10 — our recompute, not HUD's published LAI.

Run: `.venv/bin/python scripts/scoring/affordability.py`
(depends on scoring/acs_rollup.py having populated the CCA input columns).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from utils.supabase_admin import get_admin_client  # noqa: E402
from scoring import fetch_all  # noqa: E402

CTA_PASS = 75.0          # $/mo, CTA 30-day pass (2025)
PER_AUTO_ANNUAL = 12297.0  # $/yr per vehicle (AAA 2024, new-vehicle upper bound)
REFERENCE_INCOME = 75134.0  # $/yr — Chicago citywide median household income
                            # (ACS 2019–23 B19013, place=Chicago). Fixed reference;
                            # the user-salary input will replace this live.
LO, HI = 0.30, 0.60      # H+T ratio anchors: 30% ⇒ 10, 45% ⇒ 5, 60% ⇒ 0


def _transport_mo(transit_share, autos_per_hh) -> float:
    transit = (transit_share or 0.0) * CTA_PASS
    auto = (autos_per_hh or 0.0) * PER_AUTO_ANNUAL / 12.0
    return transit + auto


def _afford(ht_ratio: float) -> float:
    return round(max(0.0, min(10.0, 10.0 * (HI - ht_ratio) / (HI - LO))), 2)


def _score_grain(client, table: str) -> dict:
    """Compute H+T affordability for every row of `table` (ccas or tracts) and
    upsert. Both grains hold the same inputs (rent_median, transit_share,
    autos_per_hh); ccas.name is NOT NULL so it's carried on the CCA upsert."""
    named = table == "ccas"
    select = ("id,name," if named else "id,") + "rent_median,transit_share,autos_per_hh"
    rows = fetch_all(client, table, select, key=None if named else "id")

    payload, skipped = [], 0
    for c in rows:
        rent = c.get("rent_median")
        if not rent:
            skipped += 1
            continue
        housing_mo = float(rent)
        transport_mo = _transport_mo(c.get("transit_share"), c.get("autos_per_hh"))
        ht_ratio = (housing_mo + transport_mo) * 12.0 / REFERENCE_INCOME
        row = {
            "id": c["id"],
            "housing_cost_mo": round(housing_mo),
            "transport_cost_mo": round(transport_mo),
            "afford_score": _afford(ht_ratio),
        }
        if named:
            row["name"] = c["name"]
        payload.append(row)

    for i in range(0, len(payload), 400):
        client.table(table).upsert(payload[i:i + 400]).execute()
    return {"scored": len(payload), "skipped_no_input": skipped}


def compute() -> dict:
    client = get_admin_client()
    return {grain: _score_grain(client, grain) for grain in ("ccas", "tracts")}


if __name__ == "__main__":
    s = compute()
    print(f"affordability: ccas={s['ccas']} tracts={s['tracts']}")
