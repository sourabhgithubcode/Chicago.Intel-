// Cross-session cache for heavy, slow-changing data loads. The map's score
// datasets (ccas/tracts, quarterly refresh) and per-address amenities (30d
// server TTL) are re-fetched every session otherwise — each a cold ~0.7s+
// round-trip (amenities can be ~30s if the free-tier treasurer is asleep).
// localStorage persists them across refreshes/sessions so repeat loads are
// instant. In-session module memoization still sits in front of this.
//
// Only VALID results are cached (never an empty/failed fetch), so a transient
// outage can't pin a blank map for the whole TTL. Caller: supabase.js, amenities.js.

const nonEmpty = (d) => d != null && (!Array.isArray(d) || d.length > 0);

export async function cachedJSON(key, ttlMs, loader, isValid = nonEmpty) {
  try {
    const raw = localStorage.getItem(key);
    if (raw) {
      const { ts, data } = JSON.parse(raw);
      if (Date.now() - ts < ttlMs && isValid(data)) return data;
    }
  } catch { /* absent / corrupt / private mode — fall through to loader */ }

  const data = await loader();
  if (isValid(data)) {
    try { localStorage.setItem(key, JSON.stringify({ ts: Date.now(), data })); }
    catch { /* quota / private mode — non-fatal, just skip persisting */ }
  }
  return data;
}
