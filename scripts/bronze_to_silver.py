"""
Bronze-to-silver replay.

Downloads the latest non-empty bronze file per source from R2,
runs it through the existing transformer modules, and upserts to
the corresponding Supabase silver tables.

Use this when:
  - Loading silver tables for the first time from existing bronze
  - Re-running a clean transform after a schema change
  - Targeted single-source reload without re-hitting any API

Usage:
    cd scripts
    python bronze_to_silver.py                         # all 7 sources
    python bronze_to_silver.py --sources cpd,311,cta   # subset
    python bronze_to_silver.py --sources assessor --dry-run
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

import boto3
import structlog

sys.path.insert(0, str(Path(__file__).parent))

from utils.logging_setup import setup_logging
from utils.supabase_admin import get_admin_client
import transformers.assessor as _t_assessor
import transformers.cpd as _t_cpd
import transformers._311 as _t_311
import transformers.cta as _t_cta
import transformers.parks as _t_parks
import transformers.streets as _t_streets
from fetchers.fetch_acs import to_silver as _acs_to_silver

log = structlog.get_logger()

# ── Silver table per source ───────────────────────────────────────────────────

SILVER_TABLE = {
    "assessor": "buildings",
    "cpd":      "cpd_incidents",
    "311":      "complaints_311",
    "cta":      "cta_stops",
    "parks":    "parks",
    "streets":  "streets",
    "acs":      "tracts",
}

# Bronze prefix(es) per logical source — assessor joins 4 sub-datasets.
BRONZE_KEYS = {
    "assessor": ["assessor.universe", "assessor.addresses",
                 "assessor.characteristics", "assessor.sales"],
    "cpd":      ["cpd"],
    "311":      ["311"],
    "cta":      ["cta"],
    "parks":    ["parks"],
    "streets":  ["streets"],
    "acs":      ["acs"],
}


# ── R2 helpers ────────────────────────────────────────────────────────────────

def _s3():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def _latest_key(s3_client, bucket: str, prefix: str) -> str | None:
    """Latest non-empty key under prefix, or None if nothing exists."""
    resp = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
    objects = [o for o in resp.get("Contents", []) if o["Size"] > 0]
    if not objects:
        return None
    return max(objects, key=lambda o: o["LastModified"])["Key"]


def _download_jsonl(s3_client, bucket: str, key: str) -> list[dict]:
    """Download a .jsonl.gz and return parsed rows."""
    obj = s3_client.get_object(Bucket=bucket, Key=key)
    buf = io.BytesIO(obj["Body"].read())
    with gzip.GzipFile(fileobj=buf) as gz:
        return [json.loads(line) for line in gz if line.strip()]


# ── Transform dispatch ────────────────────────────────────────────────────────

def _transform(source: str, bronze: dict[str, list]) -> list[dict]:
    if source == "assessor":
        return _t_assessor.to_silver(
            universe=bronze["assessor.universe"],
            addresses=bronze["assessor.addresses"],
            characteristics=bronze["assessor.characteristics"],
            sales=bronze["assessor.sales"],
        )
    if source == "cpd":
        return _t_cpd.to_silver(bronze["cpd"])
    if source == "311":
        return _t_311.to_silver(bronze["311"])
    if source == "cta":
        return _t_cta.to_silver(bronze["cta"])
    if source == "parks":
        return _t_parks.to_silver(bronze["parks"])
    if source == "streets":
        return _t_streets.to_silver(bronze["streets"])
    if source == "acs":
        # ACS bronze rows were stored as {"row": [census_api_list]}
        raw = [r["row"] for r in bronze["acs"]]
        return _acs_to_silver(raw)
    raise ValueError(f"No transformer defined for source: {source!r}")


# ── Per-source runner ─────────────────────────────────────────────────────────

def run_source(source: str, s3_client, bucket: str,
               supabase=None, dry_run: bool = False) -> dict:
    """
    Download → transform → upsert one source.
    Returns a stats dict: {bronze_rows, silver_rows, dropped, table}.
    """
    log.info("source_start", source=source)
    bronze: dict[str, list] = {}

    for bkey in BRONZE_KEYS[source]:
        key = _latest_key(s3_client, bucket, f"bronze/{bkey}/")
        if not key:
            raise RuntimeError(f"No non-empty bronze object found for prefix bronze/{bkey}/")
        size_mb = s3_client.head_object(Bucket=bucket, Key=key)["ContentLength"] / 1e6
        log.info("downloading", bkey=bkey, key=key, size_mb=round(size_mb, 2))
        bronze[bkey] = _download_jsonl(s3_client, bucket, key)
        log.info("downloaded", bkey=bkey, rows=len(bronze[bkey]))

    bronze_total = sum(len(v) for v in bronze.values())
    silver = _transform(source, bronze)
    dropped = bronze_total - len(silver)

    log.info("transformed", source=source,
             bronze_rows=bronze_total, silver_rows=len(silver), dropped=dropped)

    if not silver:
        log.warning("no_silver_rows_after_transform", source=source)
        return {"bronze_rows": bronze_total, "silver_rows": 0,
                "dropped": dropped, "table": SILVER_TABLE[source]}

    if dry_run:
        log.info("dry_run_sample", source=source, sample=silver[:3])
    else:
        table = SILVER_TABLE[source]
        supabase.table(table).upsert(silver).execute()
        log.info("upserted", source=source, table=table, rows=len(silver))

    return {
        "bronze_rows": bronze_total,
        "silver_rows": len(silver),
        "dropped": dropped,
        "table": SILVER_TABLE[source],
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Replay bronze → silver without re-fetching from APIs."
    )
    parser.add_argument("--sources", default="all",
                        help="Comma-separated source names, or 'all'")
    parser.add_argument("--dry-run", action="store_true",
                        help="Transform but skip the Supabase upsert")
    args = parser.parse_args()

    setup_logging()

    sources = (list(BRONZE_KEYS.keys()) if args.sources == "all"
               else [s.strip() for s in args.sources.split(",")])

    unknown = [s for s in sources if s not in BRONZE_KEYS]
    if unknown:
        log.error("unknown_sources", sources=unknown,
                  valid=list(BRONZE_KEYS.keys()))
        sys.exit(1)

    s3_client = _s3()
    bucket = os.environ["BRONZE_BUCKET"]
    supabase = None if args.dry_run else get_admin_client()

    results: dict[str, dict] = {}
    failed: list[str] = []

    for source in sources:
        try:
            results[source] = run_source(
                source, s3_client, bucket,
                supabase=supabase, dry_run=args.dry_run
            )
        except Exception as e:
            log.error("source_failed", source=source, error=str(e))
            failed.append(source)

    # Summary table
    print("\n── Bronze → Silver Summary ──────────────────────────────")
    print(f"{'Source':<12} {'Bronze':>10} {'Silver':>10} {'Dropped':>10}  Table")
    print("─" * 60)
    for src, stats in results.items():
        print(f"{src:<12} {stats['bronze_rows']:>10,} {stats['silver_rows']:>10,} "
              f"{stats['dropped']:>10,}  {stats['table']}")
    if failed:
        print(f"\nFAILED: {', '.join(failed)}")
    print()


if __name__ == "__main__":
    main()
