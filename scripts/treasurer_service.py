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

import hashlib
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


def _parse_ts(s: str) -> datetime:
    # Postgres returns timestamps like '2026-05-11T04:49:01.006850+00:00'.
    # Python 3.9 fromisoformat is strict about microsecond digits — strip
    # the fractional part since second-level resolution is enough for TTL.
    s = re.sub(r"\.\d+", "", s.replace("Z", "+00:00"))
    return datetime.fromisoformat(s)


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
                 _parse_ts(row["fetched_at"])).total_seconds()
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


# FEMA NFHL flood zone — per-coordinate lookup, 1yr cache.
# Free, keyless, ArcGIS REST. Returns FLD_ZONE (X/A/AE/VE/etc) + subtype.
FEMA_URL = (
    "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/"
    "MapServer/28/query"
)
FEMA_TTL_SECONDS = 365 * 24 * 60 * 60


@app.get("/flood-zone")
def flood_zone():
    try:
        lat = float(request.args.get("lat", ""))
        lng = float(request.args.get("lng", ""))
    except ValueError:
        return jsonify({"error": "lat and lng required as floats"}), 400

    coord_key = f"{lat:.4f},{lng:.4f}"
    client = get_admin_client()

    cached = (client.table("fema_cache")
              .select("flood_zone,zone_subtype,fetched_at")
              .eq("coord_key", coord_key).limit(1).execute().data or [])
    if cached:
        row = cached[0]
        age_s = (datetime.now(timezone.utc) -
                 _parse_ts(row["fetched_at"])).total_seconds()
        if age_s < FEMA_TTL_SECONDS:
            return jsonify({**row, "cached": True})

    try:
        r = requests.get(FEMA_URL, params={
            "where": "1=1",
            "geometry": f"{lng},{lat}",
            "geometryType": "esriGeometryPoint",
            "inSR": "4326",
            "outFields": "FLD_ZONE,ZONE_SUBTY",
            "returnGeometry": "false",
            "f": "json",
        }, timeout=30)
        r.raise_for_status()
        features = (r.json().get("features") or [])
        if features:
            attrs = features[0].get("attributes") or {}
            zone = attrs.get("FLD_ZONE")
            subtype = attrs.get("ZONE_SUBTY")
        else:
            # No FIRM polygon covering the point — outside floodplain entirely.
            zone, subtype = "X", "OUTSIDE MAPPED FLOOD HAZARD AREA"
    except Exception as e:
        return jsonify({"error": "fema lookup failed", "detail": str(e)}), 500

    row = {
        "coord_key": coord_key,
        "flood_zone": zone,
        "zone_subtype": subtype,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        client.table("fema_cache").upsert([row]).execute()
    except Exception as e:
        return jsonify({"error": "cache upsert failed", "detail": str(e)}), 500

    return jsonify({
        "flood_zone": zone,
        "zone_subtype": subtype,
        "fetched_at": row["fetched_at"],
        "cached": False,
    })


# AirNow current AQI by ZIP code — free, keyless signup. 1h cache.
AIRNOW_URL = "https://www.airnowapi.org/aq/observation/zipCode/current/"
AIRNOW_TTL_SECONDS = 60 * 60


@app.get("/aqi")
def aqi():
    zip_code = (request.args.get("zip") or "").strip()
    if not re.fullmatch(r"\d{5}", zip_code):
        return jsonify({"error": "zip must be 5 digits"}), 400
    api_key = os.environ.get("AIRNOW_API_KEY")
    if not api_key:
        return jsonify({"error": "AIRNOW_API_KEY not configured"}), 503

    client = get_admin_client()
    cached = (client.table("aqi_cache")
              .select("zip,aqi,primary_pollutant,category,source_observed_at,fetched_at")
              .eq("zip", zip_code).limit(1).execute().data or [])
    if cached:
        row = cached[0]
        age_s = (datetime.now(timezone.utc) -
                 _parse_ts(row["fetched_at"])).total_seconds()
        if age_s < AIRNOW_TTL_SECONDS:
            return jsonify({**row, "cached": True})

    try:
        r = requests.get(AIRNOW_URL, params={
            "format": "application/json",
            "zipCode": zip_code,
            "API_KEY": api_key,
        }, timeout=20)
        r.raise_for_status()
        observations = r.json() or []
    except Exception as e:
        return jsonify({"error": "airnow lookup failed", "detail": str(e)}), 500

    if not observations:
        return jsonify({"error": "no observations for that zip"}), 404

    # Pick the worst AQI across reported parameters (PM2.5, O3, etc.)
    worst = max(observations, key=lambda o: o.get("AQI") or 0)
    observed = f"{worst.get('DateObserved','').strip()} {worst.get('HourObserved','')}:00"
    row = {
        "zip": zip_code,
        "aqi": worst.get("AQI"),
        "primary_pollutant": worst.get("ParameterName"),
        "category": (worst.get("Category") or {}).get("Name"),
        "source_observed_at": observed,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "row_hash": hashlib.md5(
            f"{zip_code}|{worst.get('AQI')}|{observed}".encode()
        ).hexdigest(),
    }
    try:
        client.table("aqi_cache").upsert([row]).execute()
    except Exception as e:
        return jsonify({"error": "cache upsert failed", "detail": str(e)}), 500

    return jsonify({**row, "cached": False})


# RentCast rent estimate per PIN — paid per call. Aggressive 30d cache.
RENTCAST_URL = "https://api.rentcast.io/v1/avm/rent/long-term"
RENTCAST_TTL_SECONDS = 30 * 24 * 60 * 60


@app.get("/rent")
def rent():
    pin = re.sub(r"\D", "", request.args.get("pin", ""))
    if not re.fullmatch(r"\d{14}", pin):
        return jsonify({"error": "pin must be 14 digits"}), 400
    try:
        bedrooms = int(request.args.get("bedrooms", "2"))
    except ValueError:
        return jsonify({"error": "bedrooms must be int"}), 400
    if bedrooms < 0 or bedrooms > 10:
        return jsonify({"error": "bedrooms 0-10"}), 400
    address = (request.args.get("address") or "").strip()
    if not address:
        return jsonify({"error": "address required"}), 400
    api_key = os.environ.get("RENTCAST_API_KEY")
    if not api_key:
        return jsonify({"error": "RENTCAST_API_KEY not configured"}), 503

    client = get_admin_client()
    cached = (client.table("rent_cache")
              .select("pin,bedrooms,rent,rent_low,rent_high,fetched_at")
              .eq("pin", pin).eq("bedrooms", bedrooms).limit(1).execute().data or [])
    if cached:
        row = cached[0]
        age_s = (datetime.now(timezone.utc) -
                 _parse_ts(row["fetched_at"])).total_seconds()
        if age_s < RENTCAST_TTL_SECONDS:
            return jsonify({**row, "cached": True})

    try:
        r = requests.get(RENTCAST_URL, headers={"X-Api-Key": api_key}, params={
            "address": address,
            "bedrooms": bedrooms,
        }, timeout=30)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return jsonify({"error": "rentcast lookup failed", "detail": str(e)}), 500

    row = {
        "pin": pin,
        "bedrooms": bedrooms,
        "rent": data.get("rent"),
        "rent_low": data.get("rentRangeLow"),
        "rent_high": data.get("rentRangeHigh"),
        "comparables": data.get("comparables"),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        client.table("rent_cache").upsert([row]).execute()
    except Exception as e:
        return jsonify({"error": "cache upsert failed", "detail": str(e)}), 500

    return jsonify({k: v for k, v in row.items() if k != "comparables"} | {"cached": False})


# Google Places (New) Nearby Search — $200/mo free credit. 30d cache.
GPLACES_URL = "https://places.googleapis.com/v1/places:searchNearby"
GPLACES_TTL_SECONDS = 30 * 24 * 60 * 60

_PLACE_TYPE_MAP = {
    "grocery":   "grocery_store",
    "gym":       "gym",
    "pharmacy":  "pharmacy",
    "coffee":    "cafe",
    "restaurant":"restaurant",
    "park":      "park",
    "bank":      "bank",
    "laundry":   "laundry",
}


@app.get("/amenities")
def amenities():
    try:
        lat = float(request.args.get("lat", ""))
        lng = float(request.args.get("lng", ""))
    except ValueError:
        return jsonify({"error": "lat and lng required"}), 400
    category = (request.args.get("category") or "").strip().lower()
    place_type = _PLACE_TYPE_MAP.get(category)
    if not place_type:
        return jsonify({"error": f"unknown category; allowed: {sorted(_PLACE_TYPE_MAP)}"}), 400
    api_key = os.environ.get("GOOGLE_PLACES_KEY")
    if not api_key:
        return jsonify({"error": "GOOGLE_PLACES_KEY not configured"}), 503

    addr_key = f"{lat:.4f},{lng:.4f}"
    client = get_admin_client()
    cached = (client.table("amenities_cache")
              .select("name,distance_m,price_level,place_id,cached_at,expires_at")
              .eq("address_key", addr_key).eq("category", category)
              .execute().data or [])
    if cached:
        first = cached[0]
        age_s = (datetime.now(timezone.utc) -
                 _parse_ts(first["cached_at"])).total_seconds()
        if age_s < GPLACES_TTL_SECONDS:
            return jsonify({"category": category, "places": cached, "cached": True})

    try:
        r = requests.post(GPLACES_URL, json={
            "includedTypes": [place_type],
            "locationRestriction": {"circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": 402,
            }},
            "maxResultCount": 10,
        }, headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": "places.displayName,places.priceLevel,places.location,places.id",
        }, timeout=20)
        r.raise_for_status()
        places = (r.json().get("places") or [])
    except Exception as e:
        return jsonify({"error": "google places lookup failed", "detail": str(e)}), 500

    now = datetime.now(timezone.utc).isoformat()
    expires = (datetime.now(timezone.utc) +
               __import__("datetime").timedelta(seconds=GPLACES_TTL_SECONDS)).isoformat()
    rows = []
    for p in places:
        ploc = p.get("location") or {}
        plat, plng = ploc.get("latitude"), ploc.get("longitude")
        dist = None
        if plat is not None and plng is not None:
            # crude planar distance — close enough at this scale (≤402m)
            dist = int(((plat - lat) ** 2 + (plng - lng) ** 2) ** 0.5 * 111_000)
        rows.append({
            "address_key": addr_key,
            "category": category,
            "name": (p.get("displayName") or {}).get("text"),
            "distance_m": dist,
            "price_level": _price_level_int(p.get("priceLevel")),
            "place_id": p.get("id"),
            "cached_at": now,
            "expires_at": expires,
        })
    if rows:
        try:
            client.table("amenities_cache").insert(rows).execute()
        except Exception as e:
            return jsonify({"error": "cache insert failed", "detail": str(e)}), 500

    return jsonify({"category": category, "places": rows, "cached": False})


# Mapbox Directions — driving / walking / cycling commute times. 30d cache.
# Free tier 100K req/mo well covers expected usage.
MAPBOX_URL = "https://api.mapbox.com/directions/v5/mapbox"
MAPBOX_TTL_SECONDS = 30 * 24 * 60 * 60
_MAPBOX_MODES = {"driving", "driving-traffic", "walking", "cycling"}


@app.get("/commute")
def commute():
    # Schema matches existing commute_cache: building_pin (origin) + work_lat/work_lng (dest).
    # Origin is always a known building since this is invoked from BuildingDetail.
    pin = re.sub(r"\D", "", request.args.get("pin", ""))
    if not re.fullmatch(r"\d{14}", pin):
        return jsonify({"error": "pin must be 14 digits"}), 400
    try:
        from_lat = float(request.args["from_lat"])
        from_lng = float(request.args["from_lng"])
        work_lat = float(request.args["work_lat"])
        work_lng = float(request.args["work_lng"])
    except (KeyError, ValueError):
        return jsonify({"error": "from_lat, from_lng, work_lat, work_lng required"}), 400
    mode = (request.args.get("mode") or "driving-traffic").lower()
    if mode not in _MAPBOX_MODES:
        return jsonify({"error": f"mode must be one of {sorted(_MAPBOX_MODES)}"}), 400
    token = os.environ.get("MAPBOX_TOKEN")
    if not token:
        return jsonify({"error": "MAPBOX_TOKEN not configured"}), 503

    client = get_admin_client()
    cached = (client.table("commute_cache")
              .select("building_pin,work_lat,work_lng,mode,minutes,distance_m,fetched_at")
              .eq("building_pin", pin)
              .eq("work_lat", work_lat).eq("work_lng", work_lng)
              .eq("mode", mode).limit(1).execute().data or [])
    if cached:
        row = cached[0]
        age_s = (datetime.now(timezone.utc) - _parse_ts(row["fetched_at"])).total_seconds()
        if age_s < MAPBOX_TTL_SECONDS:
            return jsonify({**row, "cached": True})

    try:
        r = requests.get(
            f"{MAPBOX_URL}/{mode}/{from_lng},{from_lat};{work_lng},{work_lat}",
            params={"access_token": token, "overview": "false"},
            timeout=20,
        )
        r.raise_for_status()
        routes = (r.json().get("routes") or [])
    except Exception as e:
        return jsonify({"error": "mapbox lookup failed", "detail": str(e)}), 500

    if not routes:
        return jsonify({"error": "no route between those points"}), 404

    top = routes[0]
    minutes = int(round(top.get("duration", 0) / 60))
    distance_m = int(top.get("distance", 0))
    row = {
        "building_pin": pin,
        "work_lat": work_lat,
        "work_lng": work_lng,
        "mode": mode,
        "minutes": minutes,
        "distance_m": distance_m,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "row_hash": hashlib.md5(
            f"{pin}|{work_lat:.4f},{work_lng:.4f}|{mode}|{minutes}".encode()
        ).hexdigest(),
    }
    try:
        client.table("commute_cache").upsert([row]).execute()
    except Exception as e:
        return jsonify({"error": "cache upsert failed", "detail": str(e)}), 500

    return jsonify({**row, "cached": False})


# HowLoud soundscore by lat/lng — paid per call. 1yr cache (noise is static).
HOWLOUD_URL = "https://api.howloud.com/v2/score"
HOWLOUD_TTL_SECONDS = 365 * 24 * 60 * 60


@app.get("/noise")
def noise():
    try:
        lat = float(request.args.get("lat", ""))
        lng = float(request.args.get("lng", ""))
    except ValueError:
        return jsonify({"error": "lat and lng required"}), 400
    api_key = os.environ.get("HOWLOUD_API_KEY")
    if not api_key:
        return jsonify({"error": "HOWLOUD_API_KEY not configured"}), 503

    coord_key = f"{lat:.4f},{lng:.4f}"
    client = get_admin_client()
    cached = (client.table("noise_cache")
              .select("coord_key,lat,lng,score,components,fetched_at")
              .eq("coord_key", coord_key).limit(1).execute().data or [])
    if cached:
        row = cached[0]
        age_s = (datetime.now(timezone.utc) - _parse_ts(row["fetched_at"])).total_seconds()
        if age_s < HOWLOUD_TTL_SECONDS:
            return jsonify({**row, "cached": True})

    try:
        r = requests.get(HOWLOUD_URL,
                         headers={"x-api-key": api_key},
                         params={"lat": lat, "lng": lng}, timeout=20)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return jsonify({"error": "howloud lookup failed", "detail": str(e)}), 500

    results = data.get("result") or []
    if not results:
        return jsonify({"error": "howloud returned no result"}), 502
    res = results[0] if isinstance(results, list) else results
    score = res.get("score")

    row = {
        "coord_key": coord_key,
        "lat": lat,
        "lng": lng,
        "score": score,
        "components": res,  # keeps airports/traffic/local + their *text fields
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "row_hash": hashlib.md5(f"{coord_key}|{score}".encode()).hexdigest(),
    }
    try:
        client.table("noise_cache").upsert([row]).execute()
    except Exception as e:
        return jsonify({"error": "cache upsert failed", "detail": str(e)}), 500

    return jsonify({**row, "cached": False})


def _price_level_int(s):
    return {
        "PRICE_LEVEL_FREE": 0,
        "PRICE_LEVEL_INEXPENSIVE": 1,
        "PRICE_LEVEL_MODERATE": 2,
        "PRICE_LEVEL_EXPENSIVE": 3,
        "PRICE_LEVEL_VERY_EXPENSIVE": 4,
    }.get(s)


# Foursquare Places v4 — vibe / lifestyle POIs. Free tier ~1000 calls/day.
# Replaces Yelp Fusion (expired-trial + TOS-unfriendly caching).
FSQ_URL = "https://places-api.foursquare.com/places/search"
FSQ_API_VERSION = "2025-06-17"
FSQ_TTL_SECONDS = 30 * 24 * 60 * 60


@app.get("/vibe")
def vibe():
    try:
        lat = float(request.args.get("lat", ""))
        lng = float(request.args.get("lng", ""))
    except ValueError:
        return jsonify({"error": "lat and lng required"}), 400
    api_key = os.environ.get("FOURSQUARE_API_KEY")
    if not api_key:
        return jsonify({"error": "FOURSQUARE_API_KEY not configured"}), 503

    addr_key = f"{lat:.4f},{lng:.4f}"
    client = get_admin_client()
    cached = (client.table("amenities_cache")
              .select("name,distance_m,price_level,place_id,cached_at,expires_at")
              .eq("address_key", addr_key).eq("category", "fsq_vibe")
              .execute().data or [])
    if cached:
        first = cached[0]
        age_s = (datetime.now(timezone.utc) - _parse_ts(first["cached_at"])).total_seconds()
        if age_s < FSQ_TTL_SECONDS:
            return jsonify({"places": cached, "cached": True})

    try:
        r = requests.get(FSQ_URL, headers={
            "Authorization": f"Bearer {api_key}",
            "X-Places-Api-Version": FSQ_API_VERSION,
            "Accept": "application/json",
        }, params={"ll": f"{lat},{lng}", "radius": 400, "limit": 15}, timeout=20)
        r.raise_for_status()
        results = (r.json().get("results") or [])
    except Exception as e:
        return jsonify({"error": "foursquare lookup failed", "detail": str(e)}), 500

    now = datetime.now(timezone.utc).isoformat()
    expires = (datetime.now(timezone.utc) +
               __import__("datetime").timedelta(seconds=FSQ_TTL_SECONDS)).isoformat()
    rows = []
    for p in results:
        plat, plng = p.get("latitude"), p.get("longitude")
        dist = None
        if plat is not None and plng is not None:
            dist = int(((plat - lat) ** 2 + (plng - lng) ** 2) ** 0.5 * 111_000)
        cats = p.get("categories") or []
        rows.append({
            "address_key": addr_key,
            "category": "fsq_vibe",
            "name": p.get("name"),
            "distance_m": dist,
            "price_level": None,
            "place_id": p.get("fsq_place_id"),
            "cached_at": now,
            "expires_at": expires,
        })
    if rows:
        try:
            client.table("amenities_cache").insert(rows).execute()
        except Exception as e:
            return jsonify({"error": "cache insert failed", "detail": str(e)}), 500

    return jsonify({"places": rows, "cached": False})


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
