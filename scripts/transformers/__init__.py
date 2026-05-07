"""Silver transformers — bronze raw rows → silver-schema rows.

Each transformer is pure: takes raw rows (list[dict]) and returns
silver-shaped rows ready to upsert into the table named in
loaders.SILVER_TABLE for that source.

Pure functions = unit-testable without network or DB.
"""
