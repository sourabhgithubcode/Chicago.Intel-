// API #1 — Supabase (Tier 1, required)
// Database + auto REST + RPC. Env: VITE_SUPABASE_URL, VITE_SUPABASE_ANON_KEY
// Failure mode: entire app down. Mitigation: retry + circuit breaker.

import { createClient } from '@supabase/supabase-js';
import { DatabaseError } from '../errors/index.js';
import { withRetry, CircuitBreaker } from '../retry/index.js';

const url = import.meta.env.VITE_SUPABASE_URL;
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

export const supabase = url && anonKey ? createClient(url, anonKey) : null;

const breaker = new CircuitBreaker({ name: 'supabase' });

export async function rpc(name, params = {}) {
  if (!supabase) throw new DatabaseError({ meta: { reason: 'no-client' } });
  return breaker.fire(() =>
    withRetry(async () => {
      const { data, error } = await supabase.rpc(name, params);
      if (error) throw new DatabaseError({ cause: error, meta: { name, params } });
      return data;
    })
  );
}

// ---- Typed query wrappers ---------------------------------------------------
// One function per RPC. Components call these — never `rpc()` directly — so
// the call sites get a stable shape and confidence/source metadata travel with
// the data instead of being re-derived in every component.

/**
 * Nearest CTA stop to a coordinate.
 * Backed by RPC `nearest_cta(lat, lng)` (003_create_functions.sql).
 *
 * @returns {Promise<{
 *   stop_name: string,
 *   lines: string[],
 *   distance_m: number,
 *   source: { id: string, label: string, url: string },
 *   confidence: number,
 * } | null>}
 */
export async function getNearestCTAStop(lat, lng) {
  const rows = await rpc('nearest_cta', { lat, lng });
  if (!rows || rows.length === 0) return null;
  const r = rows[0];
  return {
    stop_name: r.stop_name,
    lines: r.lines ?? [],
    distance_m: r.distance_m,
    source: {
      id: 'cta-gtfs',
      label: 'CTA GTFS',
      url: 'https://www.transitchicago.com/developers/gtfs.aspx',
    },
    confidence: 9,
  };
}
