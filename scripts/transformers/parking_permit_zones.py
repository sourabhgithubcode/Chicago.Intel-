"""Bronze → silver transformer for Chicago residential parking permit zones."""
from __future__ import annotations


def to_silver(rows: list[dict]) -> list[dict]:
    silver: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        props = row.get("properties") or {}
        row_id = str(props.get("row_id", "")).strip()
        street_name = (props.get("street_name") or "").strip()
        if not row_id or not street_name or row_id in seen:
            continue
        seen.add(row_id)

        addr_low = addr_high = None
        try:
            addr_low = int(props.get("address_range_low") or "")
        except (ValueError, TypeError):
            pass
        try:
            addr_high = int(props.get("address_range_high") or "")
        except (ValueError, TypeError):
            pass

        ward = None
        try:
            ward = int(props.get("ward_low") or props.get("ward_high") or "")
        except (ValueError, TypeError):
            pass

        silver.append({
            "id":               row_id,
            "zone":             (props.get("zone") or "").strip() or None,
            "street_name":      street_name,
            "street_direction": (props.get("street_direction") or "").strip() or None,
            "street_type":      (props.get("street_type") or "").strip() or None,
            "address_low":      addr_low,
            "address_high":     addr_high,
            "odd_even":         (props.get("odd_even") or "").strip() or None,
            "ward":             ward,
            "status":           (props.get("status") or "").strip() or None,
        })
    return silver
