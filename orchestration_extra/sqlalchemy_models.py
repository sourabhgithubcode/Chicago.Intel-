"""
sqlalchemy_models — SQLAlchemy 2.x ORM scaffold for the silver tables (ADDITIVE).

A typed ORM view of the four core silver tables — buildings, ccas, tracts,
cpd_incidents — plus an engine factory that builds a Postgres connection string
from SUPABASE_DB_* env vars.

────────────────────────────────────────────────────────────────────────────
⚠ THIS CANNOT CONNECT IN THIS ENVIRONMENT — same blocker as dbt.
────────────────────────────────────────────────────────────────────────────
.env holds only SUPABASE_SERVICE_KEY (a Supabase REST/PostgREST key). There is
NO direct Postgres connection string or DB password here, so SQLAlchemy — which
speaks the raw Postgres wire protocol via psycopg2 — has nothing to connect to.

To make it run you need the Supabase pooler creds in .env:
    SUPABASE_DB_HOST=aws-0-<region>.pooler.supabase.com
    SUPABASE_DB_PORT=6543                 # transaction pooler (or 5432 session)
    SUPABASE_DB_NAME=postgres
    SUPABASE_DB_USER=postgres.<project-ref>
    SUPABASE_DB_PASSWORD=<your-db-password>     # the one secret missing here

`__main__` attempts a connection and reports the missing-credential blocker
cleanly (no traceback) when SUPABASE_DB_PASSWORD is unset.

PostGIS note: `location` columns are GEOMETRY. Without GeoAlchemy2 installed,
they're mapped opaquely (server-side type) so the models import cleanly; this
scaffold is for relational columns — geometry is read/written as EWKT by the
existing transformers, not through this ORM.
"""

from __future__ import annotations

import datetime
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from sqlalchemy import (
    BigInteger, Date, Integer, Numeric, String, Text, create_engine, text,
)
from sqlalchemy.engine import Engine, URL
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


class Base(DeclarativeBase):
    pass


# ── Engine factory ────────────────────────────────────────────────────────────

REQUIRED_ENV = (
    "SUPABASE_DB_HOST",
    "SUPABASE_DB_PORT",
    "SUPABASE_DB_NAME",
    "SUPABASE_DB_USER",
    "SUPABASE_DB_PASSWORD",
)


def missing_db_env() -> list[str]:
    """Which SUPABASE_DB_* vars are unset. Empty list = ready to connect."""
    return [k for k in REQUIRED_ENV if not os.environ.get(k)]


def get_engine(echo: bool = False) -> Engine:
    """Build a psycopg2 Engine from SUPABASE_DB_* env (Supabase pooler).

    Raises RuntimeError listing the missing vars if anything required is unset —
    so callers get the credential blocker, not an opaque DNS/auth error.
    """
    missing = missing_db_env()
    if missing:
        raise RuntimeError(
            "Cannot build engine — missing env: " + ", ".join(missing) +
            ". Add the Supabase pooler creds to .env (see module docstring)."
        )
    url = URL.create(
        drivername="postgresql+psycopg2",
        username=os.environ["SUPABASE_DB_USER"],
        password=os.environ["SUPABASE_DB_PASSWORD"],
        host=os.environ["SUPABASE_DB_HOST"],
        port=int(os.environ["SUPABASE_DB_PORT"]),
        database=os.environ["SUPABASE_DB_NAME"],
    )
    return create_engine(url, echo=echo, pool_pre_ping=True)


# ── ORM models (silver schema — migrations 001 + 013 + 014) ───────────────────

class Building(Base):
    __tablename__ = "buildings"

    pin: Mapped[str] = mapped_column(String, primary_key=True)
    address: Mapped[Optional[str]] = mapped_column(Text)
    owner: Mapped[Optional[str]] = mapped_column(Text)
    purchase_price: Mapped[Optional[int]] = mapped_column(BigInteger)
    tax_status: Mapped[Optional[str]] = mapped_column(Text)
    street_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    # location GEOMETRY(POINT,4326) — handled as EWKT by transformers, not here.


class Cca(Base):
    __tablename__ = "ccas"

    cca_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[Optional[str]] = mapped_column(Text)
    median_rent: Mapped[Optional[int]] = mapped_column(Integer)
    # geometry GEOMETRY(MULTIPOLYGON,4326) — opaque here.


class Tract(Base):
    __tablename__ = "tracts"

    geoid: Mapped[str] = mapped_column(String, primary_key=True)
    median_rent: Mapped[Optional[int]] = mapped_column(Integer)
    rent_moe: Mapped[Optional[float]] = mapped_column(Numeric)
    # geometry GEOMETRY(MULTIPOLYGON,4326) — opaque here.


class CpdIncident(Base):
    __tablename__ = "cpd_incidents"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    iucr: Mapped[Optional[str]] = mapped_column(Text)
    type: Mapped[Optional[str]] = mapped_column(Text)  # CHECK violent/property/other
    date: Mapped[datetime.date] = mapped_column(Date)
    # location GEOMETRY(POINT,4326) with GIST index — opaque here.


# ── Connection probe ──────────────────────────────────────────────────────────

def main() -> int:
    missing = missing_db_env()
    print("SQLAlchemy", __import__("sqlalchemy").__version__,
          "— silver ORM scaffold (buildings, ccas, tracts, cpd_incidents)")
    print("models imported OK:",
          [m.__tablename__ for m in (Building, Cca, Tract, CpdIncident)])

    if missing:
        print("\nBLOCKER — cannot connect. Missing env:", ", ".join(missing))
        print("Reason: .env has only SUPABASE_SERVICE_KEY (a REST key), no direct")
        print("Postgres password. SQLAlchemy needs the Supabase pooler creds —")
        print("set SUPABASE_DB_PASSWORD (+ host/port/user/name). Same blocker as dbt.")
        return 0  # expected here — report cleanly, don't crash

    # Only reached when creds are present.
    try:
        engine = get_engine()
        with engine.connect() as conn:
            v = conn.execute(text("select version()")).scalar_one()
            n = conn.execute(text("select count(*) from cpd_incidents")).scalar_one()
        print("\nCONNECTED:", v)
        print("cpd_incidents rows:", f"{n:,}")
        return 0
    except Exception as e:
        print(f"\nConnection attempt failed ({type(e).__name__}): {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
