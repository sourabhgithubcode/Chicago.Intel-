"""Validate REAL transformer output against the Pydantic silver models.

Additive validation layer. Pulls a small bronze sample from R2, runs the real
`scripts.transformers.<source>.to_silver` over it (no DB writes), and validates
every produced silver row against its `validation.models` model. This is the
gate for lifting the data-load freeze: a source whose transformer output
validates clean can have `--bronze-only` dropped from its render.yaml cron.

Run:
    .venv/bin/python validation/validate_transformer_output.py [--source cpd|311] [RUN_ID] [--limit N]

Env (read from .env via python-dotenv, never hardcoded):
    BRONZE_BUCKET, R2_ENDPOINT, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY

Bronze key shape (from scripts/utils/bronze_store.py):
    s3://{BRONZE_BUCKET}/bronze/{prefix}/{run_id}.jsonl.gz
If no RUN_ID is given we list the source's prefix and use the most recent object.

Only single-iterable `to_silver(rows)` sources live here (cpd, 311). The
assessor transformer takes four separate bronze datasets and is validated
separately when its monthly cron is un-frozen.
"""
from __future__ import annotations

import gzip
import io
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from pydantic import ValidationError

# Make repo root importable so we can call the REAL transformer.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.transformers import cpd as cpd_transformer  # noqa: E402
from scripts.transformers import _311 as _311_transformer  # noqa: E402
from validation.models import CpdIncident, Complaint311  # noqa: E402

load_dotenv(ROOT / ".env")

SAMPLE_LIMIT = 5000

# source -> (bronze prefix, transformer.to_silver, pydantic model)
SOURCES = {
    "cpd": ("cpd", cpd_transformer.to_silver, CpdIncident),
    "311": ("311", _311_transformer.to_silver, Complaint311),
}


def _r2_client():
    import boto3
    return boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def _latest_run_id(client, bucket: str, prefix: str) -> str | None:
    resp = client.list_objects_v2(Bucket=bucket, Prefix=f"bronze/{prefix}/")
    objs = resp.get("Contents", [])
    if not objs:
        return None
    newest = max(objs, key=lambda o: o["LastModified"])
    return Path(newest["Key"]).name.replace(".jsonl.gz", "")


def load_bronze_sample(run_id: str | None, limit: int, prefix: str) -> tuple[list[dict], str]:
    client = _r2_client()
    bucket = os.environ["BRONZE_BUCKET"]
    if run_id is None:
        run_id = _latest_run_id(client, bucket, prefix)
        if run_id is None:
            raise SystemExit(f"No bronze/{prefix}/*.jsonl.gz objects found in R2.")
    key = f"bronze/{prefix}/{run_id}.jsonl.gz"
    body = client.get_object(Bucket=bucket, Key=key)["Body"].read()
    rows: list[dict] = []
    with gzip.GzipFile(fileobj=io.BytesIO(body)) as gz:
        for line in gz:
            if not line.strip():
                continue
            rows.append(json.loads(line))
            if len(rows) >= limit:
                break
    return rows, key


def validate(silver_rows: list[dict], model) -> dict:
    passed, failed, errors = 0, 0, []
    for i, row in enumerate(silver_rows):
        try:
            model.model_validate(row)
            passed += 1
        except ValidationError as e:
            failed += 1
            if len(errors) < 10:
                errors.append((i, row.get("id"), e.errors()[0]["msg"]))
    return {"passed": passed, "failed": failed, "errors": errors}


def main() -> int:
    argv = sys.argv[1:]
    limit = SAMPLE_LIMIT
    source = "cpd"
    positional: list[str] = []
    i = 0
    while i < len(argv):
        if argv[i] == "--limit":
            limit = int(argv[i + 1])
            i += 2
            continue
        if argv[i] == "--source":
            source = argv[i + 1]
            i += 2
            continue
        positional.append(argv[i])
        i += 1
    run_id = positional[0] if positional else None

    if source not in SOURCES:
        raise SystemExit(f"unknown --source {source!r}; choose from {sorted(SOURCES)}")
    prefix, to_silver, model = SOURCES[source]

    print(f"[1/3] Loading bronze {source} sample (limit={limit}) ...")
    raw_rows, key = load_bronze_sample(run_id, limit, prefix)
    print(f"      loaded {len(raw_rows)} raw bronze rows from s3://"
          f"{os.environ['BRONZE_BUCKET']}/{key}")

    print(f"[2/3] Running REAL scripts.transformers.{source}.to_silver ...")
    silver_rows = to_silver(raw_rows)
    print(f"      transformer produced {len(silver_rows)} silver rows "
          f"({len(raw_rows) - len(silver_rows)} dropped by transformer)")

    print(f"[3/3] Validating silver rows against models.{model.__name__} ...")
    res = validate(silver_rows, model)
    total = res["passed"] + res["failed"]
    print("\n=== RESULT ===")
    print(f"validated : {total}")
    print(f"PASS      : {res['passed']}")
    print(f"FAIL      : {res['failed']}")
    if res["errors"]:
        print("\nsample failures (row_idx, id, msg):")
        for idx, rid, msg in res["errors"]:
            print(f"  - [{idx}] id={rid}: {msg}")
    ok = res["failed"] == 0 and total > 0
    print("\nstatus:", "OK" if ok else "FAILURES PRESENT")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
