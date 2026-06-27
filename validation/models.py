"""Pydantic v2 models for Chicago.Intel silver rows.

Validation layer ONLY — additive, never imported by scripts/. These models
mirror the CHECK / NOT-NULL constraints in
supabase/migrations/013_data_integrity_constraints.sql (plus the table
definitions in 001) so that transformer output can be validated *before* it
ever reaches Supabase.

Silver rows carry geometry as EWKT strings, e.g.
    "SRID=4326;POINT(-87.63 41.88)"
which is what the transformers emit. We parse the point out and range-check it
against the same Chicago bbox the DB uses (`in_chicago_bbox()`).
"""
from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator

# Chicago bbox — identical to in_chicago_bbox() in migration 013.
CHI_W, CHI_E = -87.940, -87.524
CHI_S, CHI_N = 41.644, 42.023

_POINT_RE = re.compile(r"POINT\s*\(\s*(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s*\)")


def point_in_bbox(ewkt: str) -> str:
    """Validate an EWKT POINT string lies inside the Chicago bbox.

    Returns the string unchanged on success; raises ValueError otherwise.
    Shared by every model with a `location` column (cpd, 311, buildings).
    """
    m = _POINT_RE.search(ewkt or "")
    if not m:
        raise ValueError(f"not a parseable EWKT POINT: {ewkt!r}")
    lng, lat = float(m.group(1)), float(m.group(2))
    if not (CHI_W <= lng <= CHI_E and CHI_S <= lat <= CHI_N):
        raise ValueError(f"point ({lng},{lat}) outside Chicago bbox")
    return ewkt


class CpdIncident(BaseModel):
    """cpd_incidents silver row (migrations 001 + 013 + 014/025)."""
    model_config = ConfigDict(extra="forbid")

    id: int
    iucr: str
    type: str
    date: str  # 'YYYY-MM-DD'
    location: str

    @field_validator("type")
    @classmethod
    def _type_in_set(cls, v: str) -> str:
        if v not in {"violent", "property", "other"}:
            raise ValueError(f"type must be violent/property/other, got {v!r}")
        return v

    @field_validator("date")
    @classmethod
    def _date_shape(cls, v: str) -> str:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
            raise ValueError(f"date not YYYY-MM-DD: {v!r}")
        return v

    @field_validator("location")
    @classmethod
    def _loc_bbox(cls, v: str) -> str:
        return point_in_bbox(v)


class Complaint311(BaseModel):
    """complaints_311 silver row (001 + 013: date present, location in bbox)."""
    model_config = ConfigDict(extra="forbid")

    id: int
    type: Optional[str] = None
    address: Optional[str] = None
    date: str  # 013: complaints_311_date_present
    location: str

    @field_validator("date")
    @classmethod
    def _date_shape(cls, v: str) -> str:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
            raise ValueError(f"date not YYYY-MM-DD: {v!r}")
        return v

    @field_validator("location")
    @classmethod
    def _loc_bbox(cls, v: str) -> str:
        return point_in_bbox(v)


class Building(BaseModel):
    """buildings silver row (001 + 013).

    013 enforces: address_norm present, purchase_price >= 0, tax_annual >= 0,
    year_built in 1830..2100, location in Chicago bbox. address is NOT NULL in
    001. Extra columns from the assessor transformer are allowed.
    """
    model_config = ConfigDict(extra="allow")

    pin: str
    address: str
    address_norm: str  # 013: buildings_address_norm_present
    year_built: Optional[int] = None
    purchase_price: Optional[int] = None
    tax_annual: Optional[int] = None
    location: Optional[str] = None

    @field_validator("year_built")
    @classmethod
    def _year_sane(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (1830 <= v <= 2100):
            raise ValueError(f"year_built out of 1830..2100: {v}")
        return v

    @field_validator("purchase_price", "tax_annual")
    @classmethod
    def _nonneg(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 0:
            raise ValueError(f"must be >= 0, got {v}")
        return v

    @field_validator("location")
    @classmethod
    def _loc_bbox(cls, v: Optional[str]) -> Optional[str]:
        return None if v is None else point_in_bbox(v)


class Cca(BaseModel):
    """ccas silver row (001). id 1..77, scores 0..10 or null, rent > 0 or null."""
    model_config = ConfigDict(extra="allow")

    id: int
    name: str
    rent_median: Optional[int] = None
    safety_score: Optional[float] = None
    walk_score: Optional[float] = None
    run_score: Optional[float] = None
    vibe_score: Optional[float] = None
    disp_score: Optional[float] = None

    @field_validator("id")
    @classmethod
    def _id_range(cls, v: int) -> int:
        if not 1 <= v <= 77:
            raise ValueError(f"cca id must be 1..77, got {v}")
        return v

    @field_validator("rent_median")
    @classmethod
    def _rent_pos(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v <= 0:
            raise ValueError(f"rent_median must be > 0, got {v}")
        return v

    @field_validator("safety_score", "walk_score", "run_score",
                     "vibe_score", "disp_score")
    @classmethod
    def _score_range(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and not (0 <= v <= 10):
            raise ValueError(f"score must be 0..10, got {v}")
        return v


class Tract(BaseModel):
    """tracts silver row (001 + 013). id is an 11-digit census GEOID."""
    model_config = ConfigDict(extra="allow")

    id: str
    cca_id: Optional[int] = None
    rent_median: Optional[int] = None
    safety_score: Optional[float] = None
    walk_score: Optional[float] = None
    population: Optional[int] = None
    disp_score: Optional[float] = None

    @field_validator("id")
    @classmethod
    def _geoid_shape(cls, v: str) -> str:
        if not re.fullmatch(r"\d{11}", v):
            raise ValueError(f"tract geoid must be 11 digits, got {v!r}")
        return v

    @field_validator("population")
    @classmethod
    def _pop_nonneg(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 0:
            raise ValueError(f"population must be >= 0, got {v}")
        return v

    @field_validator("safety_score", "walk_score", "disp_score")
    @classmethod
    def _score_range(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and not (0 <= v <= 10):
            raise ValueError(f"score must be 0..10, got {v}")
        return v
