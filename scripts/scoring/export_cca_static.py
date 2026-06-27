"""Export the 77 CCAs (scores + simplified geometry) to src/data/ccas.json.

This is the static fallback the frontend uses when the anon SELECT policy on
`ccas` is not yet applied (migration 026) — see src/lib/api/ccaStatic.js. CCA
scores are slow-changing reference data, so a periodically-regenerated snapshot
is fine. Re-run this after recomputing scores (safety/walk/displacement).

    .venv/bin/python scripts/scoring/export_cca_static.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from shapely.geometry import mapping, shape  # noqa: E402

from utils.supabase_admin import get_admin_client  # noqa: E402
from scoring import fetch_all  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "src" / "data" / "ccas.json"
SIMPLIFY_TOL = 0.0004  # ~40 m — fine for containment + city-zoom display


def main() -> None:
    client = get_admin_client()
    rows = fetch_all(
        client, "ccas",
        "id,name,rent_median,safety_score,walk_score,vibe_score,disp_score,data_vintage,geometry",
        key="id",
    )
    features = []
    for r in rows:
        geom = shape(r.pop("geometry")).simplify(SIMPLIFY_TOL, preserve_topology=True)
        features.append({"type": "Feature", "properties": r, "geometry": mapping(geom)})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"type": "FeatureCollection", "features": features}))
    print(f"wrote {OUT} — {len(features)} CCAs, {OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
