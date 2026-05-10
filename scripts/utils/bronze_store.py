"""
Bronze layer store — writes raw API responses as gzipped JSONL to R2.

Key shape: s3://{BRONZE_BUCKET}/bronze/{source}/{run_id}.jsonl.gz

Bronze is cold storage — never read by the frontend. Only accessed during:
  - pipeline runs (auto, write only)
  - schema changes / backfills (manual)
  - audits (manual)

Required env vars: BRONZE_BUCKET, R2_ENDPOINT, R2_ACCESS_KEY_ID,
R2_SECRET_ACCESS_KEY.
"""
from __future__ import annotations

import gzip
import io
import json
import os
from typing import Iterable

import boto3
import structlog

log = structlog.get_logger()


def write_bronze(source: str, run_id: str, rows: Iterable[dict]) -> str:
    """Serialize `rows` as gzipped JSONL and upload to R2. Returns the s3 URI."""
    buf = io.BytesIO()
    count = 0
    with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
        for row in rows:
            gz.write((json.dumps(row, default=str) + "\n").encode("utf-8"))
            count += 1
    buf.seek(0)

    bucket = os.environ["BRONZE_BUCKET"]
    key = f"bronze/{source}/{run_id}.jsonl.gz"

    boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    ).put_object(Bucket=bucket, Key=key, Body=buf.getvalue())

    uri = f"s3://{bucket}/{key}"
    log.info("bronze_write_r2", source=source, run_id=run_id, uri=uri, rows=count)
    return uri
