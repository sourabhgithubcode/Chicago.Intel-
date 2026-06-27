"""
dask_transform — parallel CPD bronze→silver with Dask (ADDITIVE showcase).

Parallelizes the CPD bronze→silver transform across partitions using a Dask bag
on the local (multiprocessing-free, threaded) scheduler, then proves it matches
the canonical single-process transformer:

    scripts/transformers/cpd.py::to_silver()

The per-row work — classify_iucr() + Chicago bbox filter — is embarrassingly
parallel, so each Dask partition maps it independently. Dedup-by-id is the one
cross-partition step; it's done as a global reduction (.distinct on id) after
the parallel map, matching to_silver()'s `seen` set semantics.

Both paths consume the SAME input rows, so the row count + type breakdown must
be identical. That equality is the test.

Data source, in priority order:
  1. Real CPD bronze from R2 (boto3) — uses scripts/bronze_to_silver.py helpers
     and the R2_* / BRONZE_BUCKET env already in .env. Sampled to --limit rows.
  2. If R2 is unreachable / empty / creds missing → a deterministic synthetic
     bronze sample (clearly labeled) exercising every branch: violent / property
     / other IUCR codes, out-of-bbox coords, malformed rows, and duplicate ids.

Run it:
    .venv/bin/python orchestration_extra/dask_transform.py
    .venv/bin/python orchestration_extra/dask_transform.py --limit 50000
    .venv/bin/python orchestration_extra/dask_transform.py --synthetic
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from dotenv import load_dotenv
load_dotenv(REPO_ROOT / ".env")

import dask.bag as db

# The canonical transformer + its shared helpers (single source of truth).
from transformers.cpd import (
    to_silver,
    classify_iucr,
    _CHI_W, _CHI_E, _CHI_S, _CHI_N,
)


# ── Per-row transform (stateless → parallelizable) ────────────────────────────

def _row_to_silver(r: dict):
    """Mirror of one to_silver() iteration WITHOUT the cross-row `seen` dedup.

    Returns a silver dict, or None to drop the row. Dedup is handled globally
    after the parallel map so partitions stay independent.
    """
    try:
        row_id = int(r["id"])
        lat = float(r["latitude"])
        lng = float(r["longitude"])
        date = r["date"][:10]
    except (KeyError, TypeError, ValueError):
        return None
    if not (_CHI_W <= lng <= _CHI_E and _CHI_S <= lat <= _CHI_N):
        return None
    iucr = r.get("iucr", "") or ""
    return {
        "id": row_id,
        "iucr": iucr,
        "type": classify_iucr(iucr),
        "date": date,
        "location": f"SRID=4326;POINT({lng} {lat})",
    }


def dask_to_silver(raw_rows: list[dict], npartitions: int = 8) -> list[dict]:
    """Parallel CPD bronze→silver via a Dask bag, returning silver rows.

    Pipeline: partition → map(_row_to_silver) → drop None → dedup by id.
    The dedup keeps first occurrence per id, matching to_silver()'s `seen` set.
    """
    bag = db.from_sequence(raw_rows, npartitions=npartitions)
    mapped = bag.map(_row_to_silver).filter(lambda x: x is not None)

    # Global dedup by id. foldby groups across partitions; we keep the first
    # non-None row seen per id (later dupes ignored), then take the values.
    deduped = mapped.foldby(
        key=lambda row: row["id"],
        binop=lambda acc, row: acc if acc is not None else row,
        initial=None,
        combine=lambda a, b: a if a is not None else b,
    )
    # foldby yields (id, row) pairs; pull the rows out and materialize.
    return [row for _id, row in deduped.compute()]


# ── Synthetic fallback sample ─────────────────────────────────────────────────

def _synthetic_rows() -> list[dict]:
    """Deterministic CPD-shaped bronze rows exercising every transform branch."""
    rows = [
        {"id": "1", "iucr": "0110", "latitude": "41.88", "longitude": "-87.63", "date": "2023-05-01T12:00:00"},  # violent
        {"id": "2", "iucr": "0810", "latitude": "41.90", "longitude": "-87.65", "date": "2023-06-01T08:30:00"},  # property (theft)
        {"id": "3", "iucr": "0820", "latitude": "41.95", "longitude": "-87.70", "date": "2023-07-01T00:00:00"},  # property
        {"id": "4", "iucr": "1330", "latitude": "41.80", "longitude": "-87.60", "date": "2023-08-01T00:00:00"},  # other
        {"id": "5", "iucr": "0560", "latitude": "41.70", "longitude": "-87.55", "date": "2023-09-01T00:00:00"},  # other (simple assault)
        {"id": "2", "iucr": "0810", "latitude": "41.90", "longitude": "-87.65", "date": "2023-06-01T08:30:00"},  # DUP of id 2
        {"id": "6", "iucr": "0820", "latitude": "40.10", "longitude": "-90.00", "date": "2023-10-01T00:00:00"},  # OUT of bbox
        {"id": "7", "iucr": "0560", "latitude": "bad", "longitude": "-87.6", "date": "2023-10-01T00:00:00"},     # malformed lat
        {"id": "8", "iucr": "031A", "latitude": "41.85", "longitude": "-87.62", "date": "2023-11-01T00:00:00"},  # violent (robbery)
        {"latitude": "41.85", "longitude": "-87.62", "date": "2023-11-01T00:00:00"},                            # missing id
    ]
    # Pad with deterministic in-bbox rows so partitions are non-trivial.
    for i in range(100, 400):
        iucr = "0810" if i % 3 == 0 else ("0110" if i % 3 == 1 else "1330")
        rows.append({"id": str(i), "iucr": iucr,
                     "latitude": f"{41.70 + (i % 30) / 100:.4f}",
                     "longitude": f"{-87.60 - (i % 30) / 100:.4f}",
                     "date": "2023-01-15T00:00:00"})
    return rows


def _load_bronze_from_r2(limit: int) -> list[dict] | None:
    """Pull a CPD bronze sample from R2 via the existing helpers. None on failure."""
    import os
    try:
        import bronze_to_silver as b2s  # scripts/bronze_to_silver.py
        bucket = os.environ["BRONZE_BUCKET"]
        s3 = b2s._s3()
        key = b2s._latest_key(s3, bucket, "bronze/cpd/")
        if not key:
            print("[r2] no non-empty bronze/cpd/ object found — using synthetic sample")
            return None
        print(f"[r2] downloading {key} …")
        rows = b2s._download_jsonl(s3, bucket, key)
        print(f"[r2] downloaded {len(rows):,} rows; sampling first {limit:,}")
        return rows[:limit]
    except Exception as e:
        print(f"[r2] unavailable ({type(e).__name__}: {e}) — using synthetic sample")
        return None


def _breakdown(silver: list[dict]) -> dict:
    return dict(Counter(r["type"] for r in silver))


def main():
    ap = argparse.ArgumentParser(description="Parallel CPD bronze→silver with Dask.")
    ap.add_argument("--limit", type=int, default=50000, help="max bronze rows to sample from R2")
    ap.add_argument("--partitions", type=int, default=8, help="Dask bag partitions")
    ap.add_argument("--synthetic", action="store_true", help="force the synthetic sample")
    args = ap.parse_args()

    if args.synthetic:
        raw, origin = _synthetic_rows(), "synthetic"
    else:
        r2 = _load_bronze_from_r2(args.limit)
        if r2 is None:
            raw, origin = _synthetic_rows(), "synthetic (R2 fallback)"
        else:
            raw, origin = r2, "R2 bronze/cpd"

    print(f"\ninput: {len(raw):,} raw rows  (source: {origin})")
    print(f"dask: scheduler=local threads, partitions={args.partitions}\n")

    dask_silver = dask_to_silver(raw, npartitions=args.partitions)
    ref_silver = to_silver(raw)  # scripts/transformers/cpd.py — canonical

    d_count, r_count = len(dask_silver), len(ref_silver)
    d_break, r_break = _breakdown(dask_silver), _breakdown(ref_silver)

    print("── Comparison: Dask vs transformers.cpd.to_silver() ─────────")
    print(f"{'metric':<16}{'dask':>12}{'to_silver()':>14}")
    print("─" * 42)
    print(f"{'silver rows':<16}{d_count:>12,}{r_count:>14,}")
    for t in ("violent", "property", "other"):
        print(f"{'  '+t:<16}{d_break.get(t,0):>12,}{r_break.get(t,0):>14,}")

    # Equality test — same id set + same per-type counts.
    ids_match = {r["id"] for r in dask_silver} == {r["id"] for r in ref_silver}
    counts_match = (d_count == r_count) and (d_break == r_break)
    ok = ids_match and counts_match
    print("\nMATCH:", "PASS ✓" if ok else "FAIL ✗",
          f"(id sets {'equal' if ids_match else 'DIFFER'}, "
          f"counts {'equal' if counts_match else 'DIFFER'})")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
