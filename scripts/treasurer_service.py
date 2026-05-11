"""Live per-PIN Cook County Treasurer scrape — HTTP service.

Replaces the Supabase Edge Function (Deno) version: Deno's strict rustls
rejected CCT's misconfigured cert chain (browsers + Python's certifi
paper over it via AIA chasing). This Flask service lives on Render's
free tier — first request after 15min idle takes ~30s (cold start);
warm requests are sub-second.

POST /treasurer-lookup
    Body:   { "pin": "<14 digits, dashes ok>" }
    Header: Authorization: Bearer <supabase anon key>
    Resp:   { tax_year, total_billed, total_paid, amount_due,
              fetched_at, cached }

Flow (matches the working POC + the old edge function):
  1. GET  taxbillhistorysearch.aspx  → parse hidden ASP.NET form fields
  2. POST setsearchparameters.aspx   → 5 PIN segments + viewstate
  3. Follow redirect to yourpropertytaxoverviewresults.aspx
  4. Regex-extract billed / paid / due / tax_year from the response text
"""
from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from flask import Flask, jsonify, request
from flask_cors import CORS

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils.supabase_admin import get_admin_client

app = Flask(__name__)
CORS(app)  # public PINs, public site — permissive CORS is fine

BASE = "https://www.cookcountytreasurer.com"
SEARCH_URL = f"{BASE}/taxbillhistorysearch.aspx"
SUBMIT_URL = f"{BASE}/setsearchparameters.aspx"

UA = "Mozilla/5.0 (compatible; chicago-intel/1.0; +https://chicago.intel)"
TTL_SECONDS = 30 * 24 * 60 * 60  # 30d


def _extract_hidden(html: str, name: str) -> str:
    m = re.search(rf'<input[^>]*name="{re.escape(name)}"[^>]*value="([^"]*)"', html, re.I)
    if not m:
        m = re.search(rf'<input[^>]*value="([^"]*)"[^>]*name="{re.escape(name)}"', html, re.I)
    if not m:
        raise RuntimeError(f"hidden field not found: {name}")
    return m.group(1)


def _strip_tags(html: str) -> str:
    s = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    s = re.sub(r"<style[\s\S]*?</style>", " ", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = s.replace("&nbsp;", " ").replace("&amp;", "&")
    return re.sub(r"\s+", " ", s).strip()


def _money(s: str | None) -> float | None:
    if not s:
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", s.replace(",", "").replace("$", ""))
    return float(m.group(0)) if m else None


def _parse_overview(text: str) -> dict:
    year = re.search(r"Tax Year\s+(\d{4})", text, re.I)
    billed = re.search(r"Total Amount Billed[:\s]*\$?([\d,]+\.\d{2})", text, re.I)
    paid = re.search(r"Total Amount Paid[:\s]*\$?([\d,]+\.\d{2})", text, re.I)
    due = re.search(r"(?:Total\s+)?Amount Due[:\s]*\$?([\d,]+\.\d{2})", text, re.I)
    return {
        "tax_year": int(year.group(1)) if year else None,
        "total_billed": _money(billed.group(1)) if billed else None,
        "total_paid": _money(paid.group(1)) if paid else None,
        "amount_due": _money(due.group(1)) if due else None,
    }


def _scrape(pin: str) -> dict:
    # NOTE: cookcountytreasurer.com serves a misconfigured cert chain — leaf is
    # Sectigo-signed but the server sends an SSL.com intermediate that doesn't
    # link. Browsers paper over it via AIA chasing; Python/Deno don't. Disable
    # verification for THIS site only — data is public, no secrets in transit,
    # worst case is reading false numbers (cached 30d, low MITM risk).
    sess = requests.Session()
    sess.headers.update({"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"})
    sess.verify = False
    requests.packages.urllib3.disable_warnings(
        requests.packages.urllib3.exceptions.InsecureRequestWarning
    )

    r = sess.get(SEARCH_URL, timeout=30)
    r.raise_for_status()
    html = r.text
    vs = _extract_hidden(html, "__VIEWSTATE")
    gen = _extract_hidden(html, "__VIEWSTATEGENERATOR")
    ev = _extract_hidden(html, "__EVENTVALIDATION")

    seg = [pin[0:2], pin[2:4], pin[4:7], pin[7:10], pin[10:14]]
    prefix = "ctl00$ContentPlaceHolder1$ASPxPanel1$SearchByPIN1"
    form = {
        "__VIEWSTATE": vs,
        "__VIEWSTATEGENERATOR": gen,
        "__EVENTVALIDATION": ev,
        f"{prefix}$txtPIN1": seg[0],
        f"{prefix}$txtPIN2": seg[1],
        f"{prefix}$txtPIN3": seg[2],
        f"{prefix}$txtPIN4": seg[3],
        f"{prefix}$txtPIN5": seg[4],
        f"{prefix}$cmdContinue": "Continue",
    }
    r2 = sess.post(SUBMIT_URL, data=form, headers={"Referer": SEARCH_URL}, timeout=30)
    r2.raise_for_status()
    text = _strip_tags(r2.text)
    parsed = _parse_overview(text)
    if parsed["tax_year"] is None and parsed["total_billed"] is None and parsed["amount_due"] is None:
        raise RuntimeError("treasurer response missing all expected fields")

    i = text.lower().find("tax year")
    snippet = text[max(0, i - 40): i + 400] if i >= 0 else text[:400]
    return {**parsed, "raw_text": snippet}


@app.post("/treasurer-lookup")
def lookup():
    # No auth — the anon key is public (compiled into the frontend bundle), so
    # a bearer check would be theatrical. Abuse protection is the 30d cache +
    # Render's free-tier rate limits.
    body = request.get_json(silent=True) or {}
    pin = re.sub(r"\D", "", str(body.get("pin", "")))
    if not re.fullmatch(r"\d{14}", pin):
        return jsonify({"error": "pin must be 14 digits"}), 400

    client = get_admin_client()

    # Cache hit (30d)
    cached = (client.table("treasurer_cache")
              .select("pin,tax_year,total_billed,total_paid,amount_due,fetched_at")
              .eq("pin", pin).limit(1).execute().data or [])
    if cached:
        row = cached[0]
        age_s = (datetime.now(timezone.utc) -
                 datetime.fromisoformat(row["fetched_at"].replace("Z", "+00:00"))).total_seconds()
        if age_s < TTL_SECONDS:
            return jsonify({**row, "cached": True})

    # Cache miss — scrape
    try:
        scraped = _scrape(pin)
    except Exception as e:
        return jsonify({"error": "treasurer scrape failed", "detail": str(e)}), 500

    row = {
        "pin": pin,
        "tax_year": scraped["tax_year"],
        "total_billed": scraped["total_billed"],
        "total_paid": scraped["total_paid"],
        "amount_due": scraped["amount_due"],
        "raw_text": scraped["raw_text"],
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        client.table("treasurer_cache").upsert([row]).execute()
    except Exception as e:
        return jsonify({"error": "cache upsert failed", "detail": str(e)}), 500

    return jsonify({**{k: v for k, v in row.items() if k != "raw_text"}, "cached": False})


@app.get("/healthz")
def health():
    return jsonify({"ok": True})


# US Census Bureau geocoder — proxied because Census doesn't return CORS
# headers, so browsers can't call it directly. Same endpoint, same response
# shape as Census; we just re-emit with this service's CORS.
@app.get("/geocode")
def geocode():
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"error": "missing q"}), 400
    if not re.search(r"chicago", q, re.I):
        q = f"{q}, Chicago, IL"
    try:
        r = requests.get(
            "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress",
            params={"address": q, "benchmark": "Public_AR_Current", "format": "json"},
            timeout=15,
        )
        r.raise_for_status()
        return jsonify(r.json())
    except Exception as e:
        return jsonify({"error": "geocode failed", "detail": str(e)}), 500
