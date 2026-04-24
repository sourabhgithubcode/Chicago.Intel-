"""Backup/restore helpers for pipeline rollback."""
import json
from pathlib import Path

BACKUP_DIR = Path("data/backups")
BACKUP_TABLES = ["ccas", "tracts", "cpd_incidents", "buildings",
                 "complaints_311", "cta_stops", "parks"]


def backup_tables(client, run_id: str) -> str:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_path = BACKUP_DIR / f"backup_{run_id}.jsonl"

    with open(backup_path, "w") as f:
        for table in BACKUP_TABLES:
            rows = client.table(table).select("*").execute().data
            f.write(json.dumps({"table": table, "rows": rows}) + "\n")

    return str(backup_path)


def restore_tables(client, run_id: str):
    backup_path = BACKUP_DIR / f"backup_{run_id}.jsonl"
    if not backup_path.exists():
        raise FileNotFoundError(f"No backup at {backup_path}")

    with open(backup_path) as f:
        for line in f:
            entry = json.loads(line)
            client.table(entry["table"]).delete().neq("id", -1).execute()
            if entry["rows"]:
                client.table(entry["table"]).insert(entry["rows"]).execute()
