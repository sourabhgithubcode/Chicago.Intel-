"""One-shot loader: UDP Chicago tract typology → displacement_typology.

Source: github.com/urban-displacement/displacement-typologies
File:   data/downloads_for_public/chicago.csv  (GEOID, Typology)

Run manually after applying migration 020. No cron — UDP data has not
refreshed since 2018; periodic re-runs would just rewrite identical rows.
"""

import csv
import io
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from utils.supabase_admin import get_admin_client  # noqa: E402

URL = (
    "https://raw.githubusercontent.com/urban-displacement/"
    "displacement-typologies/main/data/downloads_for_public/chicago.csv"
)


def main() -> int:
    resp = requests.get(URL, timeout=30)
    resp.raise_for_status()

    rows = [
        {"geoid": r["GEOID"].strip(), "typology": r["Typology"].strip()}
        for r in csv.DictReader(io.StringIO(resp.text))
        if r.get("GEOID") and r.get("Typology")
    ]

    get_admin_client().table("displacement_typology").upsert(rows).execute()
    print(f"displacement_typology: upserted {len(rows)} tracts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
