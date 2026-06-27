"""PySpark reproduction of the CPD bronze -> silver transform.

ADDITIVE SHOWCASE — this does NOT touch the working pipeline in scripts/.
It reproduces scripts/transformers/cpd.py:to_silver() on Spark, in local mode
(local[*], no cluster), reading the same gzipped-JSONL bronze objects from R2.

Run:
    .venv/bin/python spark/cpd_bronze_to_silver_spark.py

Requires Java (Spark needs a JVM). Verified on Java 18 local mode.
Reads R2 creds from .env via python-dotenv. No secrets are written anywhere.

The cleaning logic is kept identical to the canonical transformer by importing
its `classify_iucr` and reusing the same Chicago bbox + dedup-by-id rules.
"""
from __future__ import annotations

import gzip
import io
import os
import sys
import tempfile

import boto3
from dotenv import load_dotenv
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import StringType

# Reuse the canonical classifier from the working pipeline (additive import).
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPTS = os.path.join(_REPO, "scripts")
sys.path.insert(0, _SCRIPTS)
# Spark forks separate Python workers for UDFs; they import the pickled-by-
# reference classify_iucr, so its module must be importable there too.
os.environ["PYTHONPATH"] = _SCRIPTS + os.pathsep + os.environ.get("PYTHONPATH", "")
from transformers.cpd import classify_iucr  # noqa: E402

# Same Chicago bbox as scripts/transformers/cpd.py / migration 013.
_CHI_W, _CHI_E = -87.940, -87.524
_CHI_S, _CHI_N = 41.644, 42.023


def _s3():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def download_latest_cpd_bronze(dest_path: str) -> str:
    """Download the latest NON-EMPTY bronze/cpd/*.jsonl.gz, decompressed to
    `dest_path` (plain JSONL). Returns the source R2 key."""
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
    with gzip.GzipFile(fileobj=buf) as gz, open(dest_path, "wb") as out:
        out.write(gz.read())
    return key


def build_silver(spark: SparkSession, jsonl_path: str):
    """Apply the same cleaning as transformers.cpd.to_silver() using Spark."""
    classify_udf = F.udf(classify_iucr, StringType())

    raw = spark.read.json(jsonl_path)
    input_count = raw.count()

    silver = (
        raw
        # numeric coords + valid id required (mirrors the try/except in to_silver)
        .withColumn("lng", F.col("longitude").cast("double"))
        .withColumn("lat", F.col("latitude").cast("double"))
        .withColumn("row_id", F.col("id").cast("long"))
        .filter(F.col("row_id").isNotNull())
        .filter(F.col("lat").isNotNull() & F.col("lng").isNotNull())
        .filter(F.col("date").isNotNull())
        # Chicago bbox
        .filter((F.col("lng") >= _CHI_W) & (F.col("lng") <= _CHI_E))
        .filter((F.col("lat") >= _CHI_S) & (F.col("lat") <= _CHI_N))
        # dedup by id
        .dropDuplicates(["row_id"])
        # type + date(YYYY-MM-DD) + WKT location, matching the silver schema
        .withColumn("iucr", F.coalesce(F.col("iucr"), F.lit("")))
        .withColumn("type", classify_udf(F.col("iucr")))
        .withColumn("date", F.substring(F.col("date"), 1, 10))
        .withColumn(
            "location",
            F.concat(F.lit("SRID=4326;POINT("), F.col("lng"),
                     F.lit(" "), F.col("lat"), F.lit(")")),
        )
        .select(F.col("row_id").alias("id"), "iucr", "type", "date", "location")
    )
    return silver, input_count


def main() -> None:
    load_dotenv(os.path.join(_REPO, ".env"))

    out_dir = os.path.join(_REPO, "spark", "out")
    os.makedirs(out_dir, exist_ok=True)
    parquet_path = os.path.join(out_dir, "cpd_silver.parquet")

    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tmp:
        jsonl_path = tmp.name
    key = download_latest_cpd_bronze(jsonl_path)

    spark = (
        SparkSession.builder
        .master("local[*]")
        .appName("cpd_bronze_to_silver_spark")
        .config("spark.sql.shuffle.partitions", "8")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")

    try:
        silver, input_count = build_silver(spark, jsonl_path)
        silver.write.mode("overwrite").parquet(parquet_path)

        output_count = silver.count()
        breakdown = {r["type"]: r["count"]
                     for r in silver.groupBy("type").count().collect()}

        print("\n==================== SPARK CPD silver ====================")
        print(f"source key        : {key}")
        print(f"parquet output    : {parquet_path}")
        print(f"input rows        : {input_count}")
        print(f"output rows       : {output_count}")
        print(f"  violent         : {breakdown.get('violent', 0)}")
        print(f"  property        : {breakdown.get('property', 0)}")
        print(f"  other           : {breakdown.get('other', 0)}")
        print("=========================================================\n")
    finally:
        spark.stop()
        os.unlink(jsonl_path)


if __name__ == "__main__":
    main()
