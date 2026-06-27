"""DuckDB server-less SQL over the CPD silver Parquet.

ADDITIVE SHOWCASE — does NOT touch the working pipeline in scripts/.
Runs analytical SQL directly against the Parquet file(s) produced by the local
processing showcase (and the Spark job, if its output exists) — no database
server, no load step. This is the "query Parquet where it sits" demo.

Run (after cpd_transform_polars.py):
    .venv/bin/python processing/duckdb_analytics.py
"""
from __future__ import annotations

import os

import duckdb

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_POLARS_PQ = os.path.join(_REPO, "processing", "out", "cpd_silver_polars.parquet")
_SPARK_PQ = os.path.join(_REPO, "spark", "out", "cpd_silver.parquet")


def _print_rows(title: str, rows, headers) -> None:
    print(f"\n{title}")
    print("  " + "".join(f"{h:>16}" for h in headers))
    for r in rows:
        print("  " + "".join(f"{str(v):>16}" for v in r))


def run_on(con: duckdb.DuckDBPyConnection, label: str, path: str) -> None:
    # DuckDB reads Parquet directly — a file glob works for Spark's part-* dir.
    src = f"'{path}/*.parquet'" if os.path.isdir(path) else f"'{path}'"
    print(f"\n================ DuckDB analytics — {label} ================")
    print(f"source: {path}")

    (total,) = con.execute(f"SELECT COUNT(*) FROM read_parquet({src})").fetchone()
    print(f"total rows: {total:,}")

    by_type = con.execute(
        f"SELECT type, COUNT(*) AS n FROM read_parquet({src}) "
        "GROUP BY type ORDER BY n DESC"
    ).fetchall()
    _print_rows("counts by type:", by_type, ["type", "count"])

    by_year = con.execute(
        f"SELECT EXTRACT(year FROM CAST(date AS DATE)) AS yr, COUNT(*) AS n "
        f"FROM read_parquet({src}) GROUP BY yr ORDER BY yr"
    ).fetchall()
    _print_rows("counts by year:", by_year, ["year", "count"])

    top_iucr = con.execute(
        f"SELECT iucr, type, COUNT(*) AS n FROM read_parquet({src}) "
        "GROUP BY iucr, type ORDER BY n DESC LIMIT 10"
    ).fetchall()
    _print_rows("top 10 IUCR codes:", top_iucr, ["iucr", "type", "count"])
    print("=" * 60)


def main() -> None:
    con = duckdb.connect()  # in-memory, server-less
    ran = False
    if os.path.exists(_POLARS_PQ):
        run_on(con, "Polars output", _POLARS_PQ)
        ran = True
    if os.path.exists(_SPARK_PQ):
        run_on(con, "Spark output", _SPARK_PQ)
        ran = True
    if not ran:
        raise SystemExit(
            "No Parquet found. Run processing/cpd_transform_polars.py first."
        )


if __name__ == "__main__":
    main()
