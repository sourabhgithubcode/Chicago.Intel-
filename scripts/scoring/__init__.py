"""Score computation modules (displacement, safety, walk, landlord).

Each module reads cleaned silver data, applies a documented + reproducible
formula, and upserts the resulting 0–10 score column. Methodology lives here
(not in ad-hoc SQL) so every published number is auditable.
"""
from __future__ import annotations

import requests

# Supabase/PostgREST caps a single response at 1000 rows regardless of `limit`.
# Scoring modules routinely read tables larger than that (tracts, buildings,
# cpd_incidents), so page via the Range header.
_PAGE = 1000


def fetch_all(client, table: str, select: str, filters: dict | None = None,
              key: str | None = None) -> list[dict]:
    """Read every row of `table`, paging past the PostgREST 1000-row cap.

    `filters` are extra PostgREST query params, e.g.
    {"type": "in.(violent,property)", "date": "gte.2021-06-26"}.

    `key` enables keyset pagination on a unique, orderable column (the PK).
    Pass it for large tables — Range/offset pagination has no stable order, so
    it duplicates and skips rows across pages; keyset (`key > last`) is both
    correct and fast. `key` must be included in `select`.
    """
    base = {"select": select, **(filters or {})}
    rows: list[dict] = []

    if key is not None:
        last = None
        while True:
            params = {**base, "order": f"{key}.asc", "limit": str(_PAGE)}
            if last is not None:
                params[key] = f"gt.{last}"
            r = requests.get(f"{client.url}/rest/v1/{table}",
                             headers=client.headers, params=params, timeout=60)
            r.raise_for_status()
            batch = r.json()
            if not batch:
                return rows
            rows.extend(batch)
            last = batch[-1][key]
            if len(batch) < _PAGE:
                return rows

    offset = 0
    while True:
        r = requests.get(
            f"{client.url}/rest/v1/{table}",
            headers={**client.headers, "Range-Unit": "items",
                     "Range": f"{offset}-{offset + _PAGE - 1}"},
            params=base,
            timeout=60,
        )
        r.raise_for_status()
        batch = r.json()
        rows.extend(batch)
        if len(batch) < _PAGE:
            return rows
        offset += _PAGE
