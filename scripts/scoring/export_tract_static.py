"""Export tracts (id, cca_id, displacement typology + simplified geometry) to
src/data/tracts.json — the static fallback for the tract breadcrumb, map tract
layer, and building-view DisplacementRisk when the anon SELECT policy on `tracts`
(migration 026) is unapplied. See src/lib/api/tractStatic.js.

    .venv/bin/python scripts/scoring/export_tract_static.py
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

OUT = Path(__file__).resolve().parents[2] / "src" / "data" / "tracts.json"
SIMPLIFY_TOL = 0.0004  # ~40 m


def main() -> None:
    client = get_admin_client()
    tracts = fetch_all(client, "tracts", "id,cca_id,geometry",
                       {"geometry": "not.is.null"}, key="id")
    typ = {d["geoid"]: d["typology"]
           for d in fetch_all(client, "displacement_typology", "geoid,typology", key="geoid")}
    features = []
    for r in tracts:
        geom = shape(r["geometry"]).simplify(SIMPLIFY_TOL, preserve_topology=True)
        features.append({
            "type": "Feature",
            "properties": {"id": r["id"], "cca_id": r["cca_id"], "typology": typ.get(r["id"])},
            "geometry": mapping(geom),
        })
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"type": "FeatureCollection", "features": features}))
    print(f"wrote {OUT} — {len(features)} tracts, {OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
