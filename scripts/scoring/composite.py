"""Composite affordability+livability score (1–10) per CCA.

Weighted blend of the eight sub-scores, then min-max normalized across the 77
CCAs to a 1–10 scale. The composite is RELATIVE (a CCA's value depends on the
others), unlike the absolute sub-scores — it answers "where does this
neighborhood rank", never "is it good". Never presented as a recommendation;
every weight is shown in the UI.

Weights (must sum to 1.0; see docs/affordability_engine_spec.md §5):
    affordability 0.40, vulnerability 0.15, safety 0.15, walk 0.10,
    displacement 0.10, vibe 0.04, bike 0.03, run 0.03

A CCA missing some sub-scores is blended over the components it HAS (weights
renormalized), so partial data still yields a composite.

Run: `.venv/bin/python scripts/scoring/composite.py`
(depends on the other scorers having populated their columns).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from utils.supabase_admin import get_admin_client  # noqa: E402
from scoring import fetch_all  # noqa: E402

# sub-score column -> weight
WEIGHTS = {
    "afford_score": 0.40,
    "vuln_score": 0.15,
    "safety_score": 0.15,
    "walk_score": 0.10,
    "disp_score": 0.10,
    "vibe_score": 0.04,
    "bike_score": 0.03,
    "run_score": 0.03,
}


def _raw(c: dict):
    """Weighted mean over the sub-scores this CCA actually has (0–10)."""
    num = den = 0.0
    for col, w in WEIGHTS.items():
        v = c.get(col)
        if v is None:
            continue
        num += w * float(v)
        den += w
    return num / den if den > 0 else None


def compute() -> dict:
    client = get_admin_client()
    cols = "id,name," + ",".join(WEIGHTS)
    ccas = fetch_all(client, "ccas", cols)

    raws = {c["id"]: _raw(c) for c in ccas}
    vals = [r for r in raws.values() if r is not None]
    if not vals:
        return {"ccas_scored": 0, "skipped_no_input": len(ccas)}
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0  # all-equal guard

    name = {c["id"]: c["name"] for c in ccas}
    payload, skipped = [], 0
    for cid, raw in raws.items():
        if raw is None:
            skipped += 1
            continue
        score = 1.0 + 9.0 * (raw - lo) / span  # min-max → [1, 10]
        payload.append({
            "id": cid,
            "name": name[cid],  # ccas.name is NOT NULL
            "composite_score": round(score, 2),
        })

    for i in range(0, len(payload), 400):
        client.table("ccas").upsert(payload[i:i + 400]).execute()

    return {"ccas_scored": len(payload), "skipped_no_input": skipped}


if __name__ == "__main__":
    s = compute()
    print(f"composite: ccas_scored={s['ccas_scored']} skipped={s['skipped_no_input']}")
