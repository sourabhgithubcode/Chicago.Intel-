"""API #7 — Chicago Data Portal / CPD Crimes (Tier 3 pipeline).

Dataset: ijzp-q8t2 (Crimes 2001-present). Env: CHICAGO_DATA_TOKEN.
With token: unlimited. Without: 1K/hr. 300K+ rows over 5 years.
"""

import os

from sodapy import Socrata

DOMAIN = "data.cityofchicago.org"
DATASET = "ijzp-q8t2"
TOKEN = os.getenv("CHICAGO_DATA_TOKEN")


def fetch_last_5_years(limit: int = 50_000) -> list:
    """Pull recent CPD incidents with lat/lng. Caller paginates until exhausted."""
    client = Socrata(DOMAIN, TOKEN)
    # TODO: paginate via $offset, filter by date >= 5 years ago, write Parquet
    # to data/processed/cpd_incidents.parquet.
    return client.get(
        DATASET,
        select="id,date,primary_type,description,latitude,longitude,iucr",
        where="latitude IS NOT NULL AND date >= '2020-01-01'",
        limit=limit,
    )


if __name__ == "__main__":
    print(f"cpd: fetched {len(fetch_last_5_years())} rows")
