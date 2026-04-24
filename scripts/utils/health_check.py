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
            result = client.table(table).select("id", count="exact").limit(1).execute()
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
