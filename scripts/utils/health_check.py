"""Post-load validation — catches silent data corruption."""
import structlog

log = structlog.get_logger()

EXPECTED_MIN_COUNTS = {
    "ccas": 77,
    "tracts": 700,
    "cpd_incidents": 100_000,
    "buildings": 50_000,
    "cta_stops": 150,
    "parks": 400,
}


def run_health_checks(client) -> bool:
    ok = True
    for table, min_count in EXPECTED_MIN_COUNTS.items():
        try:
            # 'estimated' uses the planner's reltuples for big tables (no full
            # scan) so cpd_incidents/buildings don't hit the statement timeout;
            # small tables still return an exact count. We only gate on a coarse
            # floor, so the estimate is precise enough.
            result = client.table(table).select("*", count="estimated").limit(1).execute()
            actual = result.count or 0
            if actual < min_count:
                log.error("row_count_too_low", table=table,
                         expected_min=min_count, actual=actual)
                ok = False
            else:
                log.info("row_count_ok", table=table, count=actual)
        except Exception as e:
            log.error("health_check_error", table=table, error=str(e))
            ok = False
    return ok


# --- Post-load fill-rate reconciliation (prevention guard) -------------------
# Catches the audit defect classes BEFORE they reach the dashboard:
#   - a UI score column regressing to mostly-NULL (tract safety/walk → 59% fill)
#   - an OSM signal column collapsing to mostly exactly-0.0 (coverage gap as zero)
#   - a displayed column going fully dead (100% null/zero)
#   - tracts.cca_id orphans (in-city tracts with no CCA)
#
# Severity: a breach at *_warn logs loudly (visible in cron output) but does NOT
# block — prod already sits at ~40% null on several tract scores, so a hard gate
# at the warn level would roll back every load to an equally-incomplete prior
# state. A breach at *_fail means a should-be-populated column has essentially
# collapsed; that returns False and the orchestrator rolls back. Thresholds are
# calibrated against prod (2026-06-30: max null 41.8%, max zero 44.2%) so wiring
# this in does not brick existing loads.
FILL_THRESHOLDS = {
    "null_warn": 25.0,    # should-be-filled column > 25% null  → WARN
    "null_fail": 95.0,    # ... >= 95% null (total collapse)    → FAIL (rollback)
    "zero_warn": 35.0,    # OSM signal > 35% exactly 0.0         → WARN
    "zero_fail": 95.0,    # ... >= 95% exactly 0.0               → FAIL (rollback)
    "buildings_dead": 100.0,   # sampled displayed col 100% null+zero → WARN (dead)
    "buildings_sample": 5000,
}

# table -> {"null": columns that must be populated, "zero": OSM signal columns}
# Columns are exactly the ones the dashboard reads (src/lib/api/supabase.js).
FILL_WATCH = {
    "ccas": {
        "null": ["composite_score", "afford_score", "vuln_score", "safety_score",
                 "walk_score", "disp_score", "rent_median"],
        "zero": ["vibe_score", "bike_score", "run_score"],
    },
    "tracts": {
        "null": ["composite_score", "afford_score", "vuln_score", "safety_score",
                 "walk_score", "disp_score", "rent_median", "cca_id"],
        "zero": ["vibe_score", "bike_score", "run_score"],
    },
}
# buildings is large (count=exact / is.null time out) and its event counters are
# legitimately sparse, so it gets a sample-based dead-column WARN only.
BUILDINGS_DISPLAYED = ["violations_5yr", "bug_reports", "landlord_score", "heat_complaints"]

# Which watched tables a loaded source writes. Only these get reconciled, so a
# daily cpd/311 run (touches neither ccas/tracts nor buildings) is a no-op and
# the daily success path is undisturbed.
FILL_SOURCE_TABLES = {
    "acs": ["ccas", "tracts"],
    "assessor": ["buildings"],
    "treasurer": ["buildings"],
}


def _fill_pct(client, table, col, kind):
    """Return (pct, total) where pct is the % of rows that are null (kind=
    'null') or exactly 0 (kind='zero'). Uses count=exact on the small score
    tables (instant); returns (None, 0) on an empty table."""
    # tracts spans all of Cook County, but only rows WITH geometry ever render
    # (a geometry-less suburban tract is never the containing tract of a Chicago
    # address). Scope the fill check to that renderable universe so the ~547
    # out-of-scope tracts don't trip a permanent false WARN.
    geom = table == "tracts"
    tq = client.table(table).select("id", count="exact")
    if geom:
        tq = tq.not_is_("geometry", "null")
    total = tq.limit(1).execute().count or 0
    if total == 0:
        return None, 0
    q = client.table(table).select("id", count="exact")
    if geom:
        q = q.not_is_("geometry", "null")
    q = q.is_(col, "null") if kind == "null" else q.eq(col, 0)
    n = q.limit(1).execute().count or 0
    return n / total * 100.0, total


def _judge_fill(table, col, kind, pct, total) -> bool:
    """Log at the right severity; return False only on a *_fail breach."""
    fail = FILL_THRESHOLDS[f"{kind}_fail"]
    warn = FILL_THRESHOLDS[f"{kind}_warn"]
    if pct >= fail:
        log.error("fill_rate_fail", table=table, column=col, kind=kind,
                  pct=round(pct, 1), threshold=fail, total=total)
        return False
    if pct >= warn:
        log.warning("fill_rate_warn", table=table, column=col, kind=kind,
                    pct=round(pct, 1), threshold=warn, total=total)
    else:
        log.info("fill_rate_ok", table=table, column=col, kind=kind, pct=round(pct, 1))
    return True


def _reconcile_buildings(client) -> bool:
    """Sample buildings and WARN on any displayed column that is fully dead
    (100% null/zero). WARN-only: event counters are legitimately sparse and
    some fields are pending connectors — never block a load on them."""
    sample = (client.table("buildings")
              .select(",".join(BUILDINGS_DISPLAYED))
              .limit(FILL_THRESHOLDS["buildings_sample"]).execute().data) or []
    n = len(sample)
    if n == 0:
        log.error("fill_rate_error", table="buildings", error="empty sample")
        return False
    for col in BUILDINGS_DISPLAYED:
        pct = sum(1 for r in sample if r.get(col) in (None, 0)) / n * 100.0
        if pct >= FILL_THRESHOLDS["buildings_dead"]:
            log.warning("fill_rate_dead_column", table="buildings", column=col,
                        pct=round(pct, 1), sample=n)
        else:
            log.info("fill_rate_ok", table="buildings", column=col, pct=round(pct, 1))
    return True


def reconcile_fill_rates(client, sources) -> bool:
    """Post-load fill-rate gate. Only reconciles the watched tables the loaded
    `sources` actually wrote. Returns False on a *_fail breach (orchestrator
    rolls back); WARN-level breaches log loudly but pass."""
    tables = []
    for s in sources:
        for t in FILL_SOURCE_TABLES.get(s, []):
            if t not in tables:
                tables.append(t)
    if not tables:
        return True  # nothing watched in this run (e.g. daily cpd/311)

    ok = True
    for table in tables:
        if table == "buildings":
            ok = _reconcile_buildings(client) and ok
            continue
        watch = FILL_WATCH.get(table, {})
        for kind in ("null", "zero"):
            for col in watch.get(kind, []):
                pct, total = _fill_pct(client, table, col, kind)
                if pct is None:
                    continue
                ok = _judge_fill(table, col, kind, pct, total) and ok
    return ok
