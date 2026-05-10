"""Supabase admin client — minimal PostgREST shim over `requests`.

Replaces the supabase-py library, which dragged in gotrue/storage3/realtime/
pyiceberg and a fragile httpx version chain. The orchestrator only uses
PostgREST (table CRUD + RPC), so a small shim with the same chained API
keeps every caller unchanged.

Surface (one method per current caller — no speculative additions):

    client.table(t).upsert(rows).execute()
    client.table(t).insert(rows).execute()
    client.table(t).select(cols, count=...).limit(n).execute()
    client.table(t).select(cols).eq(col, v).eq(...).order(col, desc=True).limit(n).execute()
    client.table(t).delete().neq(col, v).execute()
    client.rpc(fn, args).execute()

Each .execute() returns a result object with `.data` (parsed JSON or None)
and `.count` (int — populated when `Prefer: count=exact` was sent).
"""
from __future__ import annotations

import os
import time
from typing import Any

import requests

# PostgREST 1MB-ish body limit per write; supabase-py defaulted to ~1000-row
# chunks. CTA load is 11k rows, so chunking is required for the existing
# orchestrator path to work.
_WRITE_CHUNK = 1000

# Long uploads (e.g. CPD = ~1500 chunks) hit transient SSL/network errors.
# Retry each chunk a few times with backoff before giving up.
_MAX_RETRIES = 3
_BACKOFF_S = 2.0


class _Result:
    __slots__ = ("data", "count")

    def __init__(self, data: Any, count: int = 0):
        self.data = data
        self.count = count


class _Query:
    __slots__ = ("_c", "_t", "_method", "_payload", "_params", "_extra_headers")

    def __init__(self, client: "_Client", table: str):
        self._c = client
        self._t = table
        self._method: str | None = None
        self._payload: list[dict] | None = None
        self._params: list[tuple[str, str]] = []
        self._extra_headers: dict[str, str] = {}

    # writes
    def upsert(self, rows: list[dict]) -> "_Query":
        self._method = "POST"
        self._payload = rows
        self._extra_headers["Prefer"] = "resolution=merge-duplicates,return=minimal"
        return self

    def insert(self, rows: list[dict]) -> "_Query":
        self._method = "POST"
        self._payload = rows
        self._extra_headers["Prefer"] = "return=minimal"
        return self

    def delete(self) -> "_Query":
        self._method = "DELETE"
        return self

    # reads
    def select(self, columns: str = "*", count: str | None = None) -> "_Query":
        self._method = "GET"
        self._params.append(("select", columns))
        if count:
            self._extra_headers["Prefer"] = f"count={count}"
        return self

    # filters / modifiers
    def eq(self, column: str, value: Any) -> "_Query":
        self._params.append((column, f"eq.{value}"))
        return self

    def neq(self, column: str, value: Any) -> "_Query":
        self._params.append((column, f"neq.{value}"))
        return self

    def order(self, column: str, desc: bool = False) -> "_Query":
        self._params.append(("order", f"{column}.{'desc' if desc else 'asc'}"))
        return self

    def limit(self, n: int) -> "_Query":
        self._params.append(("limit", str(n)))
        return self

    def execute(self) -> _Result:
        url = f"{self._c.url}/rest/v1/{self._t}"
        headers = {**self._c.headers, **self._extra_headers}

        if self._method == "POST":
            # Chunk large bodies — PostgREST rejects payloads above its body limit.
            rows = self._payload or []
            if not rows:
                return _Result(data=None)
            for i in range(0, len(rows), _WRITE_CHUNK):
                chunk = rows[i:i + _WRITE_CHUNK]
                for attempt in range(_MAX_RETRIES):
                    try:
                        r = requests.post(url, headers=headers, params=self._params,
                                          json=chunk, timeout=120)
                        _raise_for(r)
                        break
                    except (requests.ConnectionError, requests.Timeout) as e:
                        if attempt == _MAX_RETRIES - 1:
                            raise
                        time.sleep(_BACKOFF_S * (2 ** attempt))
            return _Result(data=None)

        if self._method == "DELETE":
            r = requests.delete(url, headers=headers, params=self._params, timeout=120)
            _raise_for(r)
            return _Result(data=None)

        # GET
        r = requests.get(url, headers=headers, params=self._params, timeout=60)
        _raise_for(r)
        data = r.json() if r.text else None
        count = _parse_count(r.headers.get("Content-Range"))
        return _Result(data=data, count=count)


class _Rpc:
    __slots__ = ("_c", "_fn", "_args")

    def __init__(self, client: "_Client", fn: str, args: dict):
        self._c = client
        self._fn = fn
        self._args = args

    def execute(self) -> _Result:
        url = f"{self._c.url}/rest/v1/rpc/{self._fn}"
        r = requests.post(url, headers=self._c.headers, json=self._args, timeout=600)
        _raise_for(r)
        data = r.json() if r.text else None
        return _Result(data=data)


class _Client:
    def __init__(self, url: str, key: str):
        self.url = url.rstrip("/")
        self.headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

    def table(self, name: str) -> _Query:
        return _Query(self, name)

    def rpc(self, fn: str, args: dict | None = None) -> _Rpc:
        return _Rpc(self, fn, args or {})


def _raise_for(r: requests.Response) -> None:
    if r.ok:
        return
    raise requests.HTTPError(f"{r.status_code} {r.reason}: {r.text[:500]}", response=r)


def _parse_count(header: str | None) -> int:
    # PostgREST returns "0-9/123" or "*/123" when Prefer: count=exact is set.
    if not header or "/" not in header:
        return 0
    tail = header.rsplit("/", 1)[1]
    return int(tail) if tail.isdigit() else 0


def get_admin_client() -> _Client:
    return _Client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
