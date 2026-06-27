"""Great Expectations suite over a real silver table (ccas) from Supabase.

Additive validation layer. Pulls the `ccas` table via PostgREST into a pandas
DataFrame and runs a small expectation suite:
  - id is unique and not null
  - safety_score / walk_score / disp_score between 0 and 10 (nulls allowed)
  - rent_median > 0 (nulls allowed)

Uses the modern GX fluent API (>= 0.18) with an EPHEMERAL context + pandas
datasource — no on-disk project scaffold.

If great_expectations cannot be imported (e.g. dependency conflict on this
Python), we fall back to a lightweight GE-style assertion runner that checks
the SAME expectations and reports pass/fail per column. Either path RUNS and
prints a result.

Run:
    .venv/bin/python validation/great_expectations_suite.py

Env (.env via python-dotenv): SUPABASE_URL, SUPABASE_SERVICE_KEY
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

SCORE_COLS = ["safety_score", "walk_score", "disp_score"]


def fetch_ccas_df():
    import pandas as pd
    url = os.environ["SUPABASE_URL"].rstrip("/")
    key = os.environ["SUPABASE_SERVICE_KEY"]
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    cols = "id,name,rent_median," + ",".join(SCORE_COLS)
    r = requests.get(f"{url}/rest/v1/ccas",
                     headers=headers,
                     params={"select": cols, "limit": "1000"},
                     timeout=60)
    r.raise_for_status()
    return pd.DataFrame(r.json())


def run_with_gx(df) -> bool:
    import great_expectations as gx

    context = gx.get_context(mode="ephemeral")
    ds = context.sources.add_pandas("chicago_intel_validation")
    asset = ds.add_dataframe_asset(name="ccas")
    batch_request = asset.build_batch_request(dataframe=df)

    suite_name = "ccas_silver_suite"
    context.add_or_update_expectation_suite(suite_name)
    validator = context.get_validator(
        batch_request=batch_request, expectation_suite_name=suite_name
    )

    validator.expect_column_values_to_not_be_null("id")
    validator.expect_column_values_to_be_unique("id")
    validator.expect_column_values_to_be_between("id", 1, 77)
    for col in SCORE_COLS:
        # mostly handling: nulls are allowed, so only check non-null values.
        validator.expect_column_values_to_be_between(
            col, min_value=0, max_value=10, mostly=1.0
        )
    validator.expect_column_values_to_be_between(
        "rent_median", min_value=1, max_value=None, mostly=1.0
    )

    results = validator.validate()
    print("\n=== GREAT EXPECTATIONS RESULT ===")
    print(f"rows checked : {len(df)}")
    print(f"success      : {results.success}")
    for r in results.results:
        exp = r.expectation_config.expectation_type
        col = r.expectation_config.kwargs.get("column", "")
        ok = "PASS" if r.success else "FAIL"
        unexpected = r.result.get("unexpected_count", "")
        print(f"  [{ok}] {exp}({col}) unexpected={unexpected}")
    return bool(results.success)


def run_fallback(df) -> bool:
    """Lightweight GE-style assertions — same expectations, no GX dependency."""
    print("\n=== LIGHTWEIGHT GE-STYLE FALLBACK RESULT ===")
    print(f"rows checked : {len(df)}")
    checks: list[tuple[str, bool, str]] = []

    n_null_id = int(df["id"].isna().sum())
    checks.append(("id not null", n_null_id == 0, f"nulls={n_null_id}"))

    n_dupe = int(df["id"].duplicated().sum())
    checks.append(("id unique", n_dupe == 0, f"dupes={n_dupe}"))

    bad_id = int(((df["id"] < 1) | (df["id"] > 77)).sum())
    checks.append(("id in 1..77", bad_id == 0, f"out_of_range={bad_id}"))

    for col in SCORE_COLS:
        s = df[col].dropna()
        bad = int(((s < 0) | (s > 10)).sum())
        checks.append((f"{col} in 0..10 (nulls ok)", bad == 0, f"out_of_range={bad}"))

    rent = df["rent_median"].dropna()
    bad_rent = int((rent <= 0).sum())
    checks.append(("rent_median > 0 (nulls ok)", bad_rent == 0, f"nonpositive={bad_rent}"))

    all_ok = True
    for name, ok, detail in checks:
        all_ok = all_ok and ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {name} ({detail})")
    print(f"\nsuccess      : {all_ok}")
    return all_ok


def main() -> int:
    print("[1/2] Fetching ccas from Supabase REST ...")
    df = fetch_ccas_df()
    print(f"      fetched {len(df)} ccas rows; columns={list(df.columns)}")

    print("[2/2] Running expectation suite ...")
    try:
        import great_expectations  # noqa: F401
        ok = run_with_gx(df)
        engine = "great_expectations"
    except Exception as e:  # import OR runtime failure → documented fallback
        print(f"      great_expectations unavailable/failed ({type(e).__name__}: "
              f"{str(e)[:160]}); using lightweight fallback.")
        ok = run_fallback(df)
        engine = "fallback"

    print(f"\nengine: {engine}")
    print("status:", "OK" if ok else "FAILURES PRESENT")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
