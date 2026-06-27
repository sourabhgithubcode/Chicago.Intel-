"""Landlord score (0–10) for buildings, from 311 building-condition complaints.

A Building Violation 311 request is filed against a specific street address, so
complaints are attributed to buildings by NORMALIZED ADDRESS (exact match on
`buildings.address_norm`), not by spatial guessing. ~70% of complaints match a
building; the rest (intersection/format misses) are dropped, not misattributed.

Per building, over the last LOOKBACK_YEARS:
    violations_5yr = # of "Building Violation" 311s         (strong landlord signal)
    bug_reports    = # of "Rodent Baiting/Rat Complaint"    (weak/environmental)
    heat_complaints = 0   (the "No Air Conditioning" 311 type returns 0 rows in
                           this dataset, so there is no heat-complaint data to load)

    landlord_score = clamp(10 - violations_5yr*VIOL_W - bug_reports*RODENT_W, 0, 10)
    (higher = better / cleaner record)

Only buildings with ≥1 matched complaint get a score written. A clean building
keeps landlord_score NULL, meaning "no recorded violations" — we do NOT fabricate
a perfect 10 for buildings we have no signal on. Confidence 7/10 (Chicago 311 is
authoritative for violations; caveat: 70% address-match coverage, and a low score
reflects complaint VOLUME, which correlates with building size).
"""
from __future__ import annotations

import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from utils.supabase_admin import get_admin_client  # noqa: E402
from scoring import fetch_all  # noqa: E402

VIOL_W = 1.0
RODENT_W = 0.1
LOOKBACK_YEARS = 5


def _norm(a: str | None) -> str:
    return " ".join((a or "").upper().split())


def compute() -> dict:
    client = get_admin_client()
    window = (date.today() - timedelta(days=365 * LOOKBACK_YEARS)).isoformat()

    # 1) Aggregate complaints per normalized address.
    complaints = fetch_all(client, "complaints_311", "id,type,address",
                           {"date": f"gte.{window}"}, key="id")
    viol: dict[str, int] = defaultdict(int)
    rodent: dict[str, int] = defaultdict(int)
    for c in complaints:
        a = _norm(c.get("address"))
        if not a:
            continue
        if c["type"] == "Building Violation":
            viol[a] += 1
        elif c["type"] == "Rodent Baiting/Rat Complaint":
            rodent[a] += 1

    # 2) Match to buildings by address_norm. Include NOT NULL cols (address,
    #    address_norm) so the upsert's insert tuple is valid.
    buildings = fetch_all(client, "buildings", "pin,address,address_norm", key="pin")
    payload = []
    for b in buildings:
        an = b["address_norm"]
        v, r = viol.get(an, 0), rodent.get(an, 0)
        if v == 0 and r == 0:
            continue
        score = round(max(0.0, min(10.0, 10.0 - v * VIOL_W - r * RODENT_W)), 2)
        payload.append({"pin": b["pin"], "address": b["address"],
                        "address_norm": an, "violations_5yr": v,
                        "bug_reports": r, "landlord_score": score})

    # buildings is 858k rows with several indexes; a 1000-row upsert exceeds
    # Supabase's statement timeout, so write in 400-row slices.
    for i in range(0, len(payload), 400):
        client.table("buildings").upsert(payload[i:i + 400]).execute()

    scored0 = sum(1 for p in payload if p["landlord_score"] == 0)
    return {"window": window, "complaints": len(complaints),
            "buildings_total": len(buildings), "buildings_scored": len(payload),
            "at_floor_0": scored0}


if __name__ == "__main__":
    s = compute()
    print(f"landlord: window>={s['window']} complaints={s['complaints']} "
          f"buildings={s['buildings_total']} scored={s['buildings_scored']} "
          f"(at_floor_0={s['at_floor_0']})")
