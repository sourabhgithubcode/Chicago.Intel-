"""Verify the Spark CPD job matches the canonical transformer on the SAME bronze.

Loads the latest non-empty bronze/cpd object in plain Python, runs the
authoritative scripts/transformers/cpd.py:to_silver(), and compares its row
count + type breakdown against the Parquet written by
cpd_bronze_to_silver_spark.py.

Run AFTER the Spark job:
    .venv/bin/python spark/cpd_bronze_to_silver_spark.py
    .venv/bin/python spark/compare_with_transformer.py
"""
from __future__ import annotations

import gzip
import io
import os
import sys
from collections import Counter

import boto3
import pandas as pd
from dotenv import load_dotenv

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "scripts"))
from transformers.cpd import to_silver  # noqa: E402


def main() -> None:
    load_dotenv(os.path.join(_REPO, ".env"))
    s3 = boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )
    bucket = os.environ["BRONZE_BUCKET"]
    resp = s3.list_objects_v2(Bucket=bucket, Prefix="bronze/cpd/")
    objects = [o for o in resp.get("Contents", []) if o["Size"] > 0]
    key = max(objects, key=lambda o: o["LastModified"])["Key"]

    obj = s3.get_object(Bucket=bucket, Key=key)
    buf = io.BytesIO(obj["Body"].read())
    with gzip.GzipFile(fileobj=buf) as gz:
        import json
        raw = [json.loads(line) for line in gz if line.strip()]

    silver = to_silver(raw)
    ref_count = len(silver)
    ref_types = Counter(r["type"] for r in silver)

    # Spark output
    pq = os.path.join(_REPO, "spark", "out", "cpd_silver.parquet")
    sdf = pd.read_parquet(pq)
    spark_count = len(sdf)
    spark_types = Counter(sdf["type"])

    print("\n============ Transformer vs Spark (same bronze) ============")
    print(f"bronze key : {key}")
    print(f"raw rows   : {len(raw)}")
    print(f"{'metric':<12}{'transformer':>14}{'spark':>10}{'match':>8}")
    rows = [
        ("rows", ref_count, spark_count),
        ("violent", ref_types['violent'], spark_types.get('violent', 0)),
        ("property", ref_types['property'], spark_types.get('property', 0)),
        ("other", ref_types['other'], spark_types.get('other', 0)),
    ]
    all_match = True
    for name, a, b in rows:
        ok = a == b
        all_match &= ok
        print(f"{name:<12}{a:>14}{b:>10}{('YES' if ok else 'NO'):>8}")
    print("===========================================================")
    print("RESULT:", "ALL MATCH" if all_match else "MISMATCH")
    sys.exit(0 if all_match else 1)


if __name__ == "__main__":
    main()
