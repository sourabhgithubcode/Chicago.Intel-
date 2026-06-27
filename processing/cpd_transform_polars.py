"""Polars + PyArrow reproduction of the CPD bronze -> silver transform.

ADDITIVE SHOWCASE — does NOT touch the working pipeline in scripts/.
It reproduces scripts/transformers/cpd.py:to_silver() with a Polars DataFrame
(no JVM, no cluster — pure local dataframe engine), reading the same
gzipped-JSONL bronze objects from R2, and writes Parquet via PyArrow.

Run:
    .venv/bin/python processing/cpd_transform_polars.py

Reads R2 creds from .env via python-dotenv. No secrets are written anywhere.
The cleaning logic is kept identical to the canonical transformer by importing
its `classify_iucr` (applied as a Polars map) and reusing the same Chicago bbox,
dedup-by-id, and date-truncate rules. A built-in verification step then runs the
authoritative to_silver() on the SAME bronze and compares the numbers.
"""
from __future__ import annotations

import gzip
import io
import json
import os
import sys
from collections import Counter

import boto3
import polars as pl
import pyarrow.parquet as pq
from dotenv import load_dotenv

# Reuse the canonical classifier + transformer from the working pipeline.
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPTS = os.path.join(_REPO, "scripts")
sys.path.insert(0, _SCRIPTS)
from transformers.cpd import classify_iucr, to_silver  # noqa: E402

# Same Chicago bbox as scripts/transformers/cpd.py / migration 013.
_CHI_W, _CHI_E = -87.940, -87.524
_CHI_S, _CHI_N = 41.644, 42.023

_OUT = os.path.join(_REPO, "processing", "out", "cpd_silver_polars.parquet")


def _s3():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def download_latest_cpd_bronze() -> tuple[str, list[dict]]:
    """Return (key, rows) for the latest NON-EMPTY bronze/cpd/*.jsonl.gz."""
    s3 = _s3()
    bucket = os.environ["BRONZE_BUCKET"]
    resp = s3.list_objects_v2(Bucket=bucket, Prefix="bronze/cpd/")
    objects = [o for o in resp.get("Contents", []) if o["Size"] > 0]
    if not objects:
        raise SystemExit("No non-empty objects under bronze/cpd/")
    latest = max(objects, key=lambda o: o["LastModified"])
    key = latest["Key"]
    print(f"[r2] downloading s3://{bucket}/{key} ({latest['Size']} bytes)")
    obj = s3.get_object(Bucket=bucket, Key=key)
    buf = io.BytesIO(obj["Body"].read())
    with gzip.GzipFile(fileobj=buf) as gz:
        rows = [json.loads(line) for line in gz if line.strip()]
    return key, rows


def build_silver(raw_rows: list[dict]) -> pl.DataFrame:
    """Apply the same cleaning as transformers.cpd.to_silver() in Polars."""
    df = pl.DataFrame(raw_rows, infer_schema_length=None)

    # numeric coords + valid id required (mirrors the try/except in to_silver);
    # strict=False turns unparseable strings/nulls into null, then we drop them.
    df = df.with_columns(
        pl.col("id").cast(pl.Int64, strict=False).alias("row_id"),
        pl.col("latitude").cast(pl.Float64, strict=False).alias("lat"),
        pl.col("longitude").cast(pl.Float64, strict=False).alias("lng"),
    )
    df = df.filter(
        pl.col("row_id").is_not_null()
        & pl.col("lat").is_not_null()
        & pl.col("lng").is_not_null()
        & pl.col("date").is_not_null()
        # Chicago bbox
        & pl.col("lng").is_between(_CHI_W, _CHI_E)
        & pl.col("lat").is_between(_CHI_S, _CHI_N)
    )
    # dedup by id, keeping first occurrence (matches to_silver's `seen` set).
    df = df.unique(subset="row_id", keep="first", maintain_order=True)

    # type via the canonical classifier (Polars map), date YYYY-MM-DD, WKT point.
    df = df.with_columns(
        pl.col("iucr").fill_null("").alias("iucr"),
    ).with_columns(
        pl.col("iucr")
        .map_elements(classify_iucr, return_dtype=pl.Utf8)
        .alias("type"),
        pl.col("date").str.slice(0, 10).alias("date"),
        (
            pl.lit("SRID=4326;POINT(")
            + pl.col("lng").cast(pl.Utf8)
            + pl.lit(" ")
            + pl.col("lat").cast(pl.Utf8)
            + pl.lit(")")
        ).alias("location"),
    )
    return df.select(
        pl.col("row_id").alias("id"), "iucr", "type", "date", "location"
    )


def main() -> None:
    load_dotenv(os.path.join(_REPO, ".env"))
    key, raw = download_latest_cpd_bronze()

    silver = build_silver(raw)

    # Explicit PyArrow Parquet write (real pyarrow.parquet usage).
    os.makedirs(os.path.dirname(_OUT), exist_ok=True)
    table = silver.to_arrow()
    pq.write_table(table, _OUT, compression="snappy")

    breakdown = Counter(silver["type"].to_list())
    print("\n=============== POLARS CPD silver (PyArrow) ===============")
    print(f"source key        : {key}")
    print(f"parquet output    : {_OUT}")
    print(f"input rows        : {len(raw)}")
    print(f"output rows       : {silver.height}")
    print(f"  violent         : {breakdown.get('violent', 0)}")
    print(f"  property        : {breakdown.get('property', 0)}")
    print(f"  other           : {breakdown.get('other', 0)}")
    print("==========================================================")

    # ── Verify against the canonical transformer on the SAME bronze ──────────
    ref = to_silver(raw)
    ref_types = Counter(r["type"] for r in ref)
    checks = [
        ("rows", len(ref), silver.height),
        ("violent", ref_types["violent"], breakdown.get("violent", 0)),
        ("property", ref_types["property"], breakdown.get("property", 0)),
        ("other", ref_types["other"], breakdown.get("other", 0)),
    ]
    print("\n--------- Polars vs transformers.cpd.to_silver() ---------")
    print(f"{'metric':<12}{'transformer':>14}{'polars':>10}{'match':>8}")
    all_match = True
    for name, a, b in checks:
        ok = a == b
        all_match &= ok
        print(f"{name:<12}{a:>14}{b:>10}{('YES' if ok else 'NO'):>8}")
    print("----------------------------------------------------------")
    print("RESULT:", "ALL MATCH" if all_match else "MISMATCH")
    sys.exit(0 if all_match else 1)


if __name__ == "__main__":
    main()
