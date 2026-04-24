"""
Bronze layer store — writes raw API responses as gzipped JSONL.

Two backends:
  - local: data/bronze/{source}/{run_id}.jsonl.gz  (dev default)
  - r2:    s3://{BRONZE_BUCKET}/bronze/{source}/{run_id}.jsonl.gz

Switch with BRONZE_BACKEND=local|r2 env var.

Bronze is cold storage — never read by the frontend. Only accessed during:
  - pipeline runs (auto)
  - schema changes / backfills (manual)
  - audits (manual)
"""

import gzip
import json
import os
from pathlib import Path
from typing import Iterable

import structlog

log = structlog.get_logger()

BACKEND = os.getenv("BRONZE_BACKEND", "local")
LOCAL_ROOT = Path(os.getenv("BRONZE_LOCAL_ROOT", "data/bronze"))


def write_bronze(source: str, run_id: str, rows: Iterable[dict]) -> str:
    """
    Serialize `rows` as gzipped JSONL, write to the configured backend,
    return the storage path (local path or s3 URI).
    """
    if BACKEND == "local":
        return _write_local(source, run_id, rows)
    if BACKEND == "r2":
        return _write_r2(source, run_id, rows)
    raise ValueError(f"Unknown BRONZE_BACKEND: {BACKEND}")


def _write_local(source: str, run_id: str, rows: Iterable[dict]) -> str:
    out_dir = LOCAL_ROOT / source
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{run_id}.jsonl.gz"

    count = 0
    with gzip.open(out_path, "wt", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, default=str) + "\n")
            count += 1

    log.info("bronze_write_local", source=source, run_id=run_id,
             path=str(out_path), rows=count)
    return str(out_path)


def _write_r2(source: str, run_id: str, rows: Iterable[dict]) -> str:
    import boto3

    bucket = os.environ["BRONZE_BUCKET"]
    endpoint = os.environ["R2_ENDPOINT"]
    access_key = os.environ["R2_ACCESS_KEY_ID"]
    secret_key = os.environ["R2_SECRET_ACCESS_KEY"]

    tmp_path = LOCAL_ROOT / source / f"{run_id}.jsonl.gz"
    tmp_path.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    with gzip.open(tmp_path, "wt", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, default=str) + "\n")
            count += 1

    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
    )

    key = f"bronze/{source}/{run_id}.jsonl.gz"
    client.upload_file(str(tmp_path), bucket, key)

    uri = f"s3://{bucket}/{key}"
    log.info("bronze_write_r2", source=source, run_id=run_id,
             uri=uri, rows=count)
    return uri


def read_bronze(source: str, run_id: str) -> list[dict]:
    """Read a bronze file back as list of dicts. For audit/replay."""
    if BACKEND == "local":
        path = LOCAL_ROOT / source / f"{run_id}.jsonl.gz"
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return [json.loads(line) for line in f]

    if BACKEND == "r2":
        import boto3
        bucket = os.environ["BRONZE_BUCKET"]
        endpoint = os.environ["R2_ENDPOINT"]
        client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        )
        tmp = LOCAL_ROOT / source / f"{run_id}.jsonl.gz"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        client.download_file(bucket, f"bronze/{source}/{run_id}.jsonl.gz", str(tmp))
        with gzip.open(tmp, "rt", encoding="utf-8") as f:
            return [json.loads(line) for line in f]

    raise ValueError(f"Unknown BRONZE_BACKEND: {BACKEND}")
