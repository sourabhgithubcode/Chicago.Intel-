"""
Chicago.Intel — Data Pipeline Orchestrator

Runs the full quarterly refresh:
  1. backup current data
  2. fetch from each source
  3. validate fetched data
  4. load into Supabase
  5. health check
  6. rollback if anything fails

Usage:
    python orchestrator.py --sources all
    python orchestrator.py --sources cta,parks
    python orchestrator.py --sources acs --dry-run
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

# Load .env from repo root before anything reads os.environ.
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

sys.path.insert(0, str(Path(__file__).parent))

import structlog
from utils.logging_setup import setup_logging
from utils.supabase_admin import get_admin_client
from utils.backup import backup_tables, restore_tables
from utils.health_check import run_health_checks

from fetchers import fetch_acs, fetch_cpd, fetch_assessor, fetch_311
from fetchers import fetch_cta, fetch_parks, fetch_streets, fetch_treasurer

# Fetchers missing run() are acceptable — only the ones you request need it.
# Order matters for downstream reconcile: assessor must run before treasurer
# (treasurer enriches buildings rows that assessor created); streets should
# run before any reconcile step that wants to populate buildings.street_id.
_MODULES = {
    "acs": fetch_acs,
    "cpd": fetch_cpd,
    "assessor": fetch_assessor,
    "311": fetch_311,
    "cta": fetch_cta,
    "parks": fetch_parks,
    "streets": fetch_streets,
    "treasurer": fetch_treasurer,
}
SOURCES = {name: getattr(mod, "run", None) for name, mod in _MODULES.items()}

log = structlog.get_logger()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", default="all")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-backup", action="store_true")
    args = parser.parse_args()

    setup_logging()
    sources = list(SOURCES.keys()) if args.sources == "all" else args.sources.split(",")

    log.info("pipeline_start", sources=sources, dry_run=args.dry_run)
    run_id = datetime.utcnow().strftime("%Y%m%dT%H%M%S")

    # Defer Supabase client creation — --dry-run doesn't need it
    client = None if args.dry_run else get_admin_client()

    # 1. Backup
    if not args.skip_backup and not args.dry_run:
        try:
            backup_path = backup_tables(client, run_id)
            log.info("backup_complete", path=backup_path)
        except Exception as e:
            log.error("backup_failed", error=str(e))
            sys.exit(1)

    # 2. Fetch
    fetched = {}
    for source in sources:
        if source not in SOURCES:
            log.error("unknown_source", source=source)
            continue
        if SOURCES[source] is None:
            log.error("fetcher_not_implemented", source=source,
                      hint="Module is missing a run(run_id: str) function.")
            sys.exit(1)
        try:
            fetched[source] = SOURCES[source](run_id=run_id)
            log.info("fetch_complete", source=source,
                     rows=len(fetched[source]) if fetched[source] else 0)
        except Exception as e:
            log.error("fetch_failed", source=source, error=str(e))
            sys.exit(1)

    # 3. Validate
    errors = []
    for source, rows in fetched.items():
        if not rows:
            errors.append(f"{source}: no rows returned")
    if errors:
        log.error("validation_failed", errors=errors)
        sys.exit(1)

    if args.dry_run:
        log.info("dry_run_complete")
        return

    # 4. Load — delegated to loaders
    try:
        from loaders import load_all
        load_all(client, fetched)
        log.info("load_complete")
    except Exception as e:
        log.error("load_failed", error=str(e))
        if not args.skip_backup:
            restore_tables(client, run_id)
        sys.exit(1)

    # 5. Health check
    if not run_health_checks(client):
        log.error("health_check_failed")
        if not args.skip_backup:
            restore_tables(client, run_id)
        sys.exit(1)

    log.info("pipeline_complete", run_id=run_id)


if __name__ == "__main__":
    main()
