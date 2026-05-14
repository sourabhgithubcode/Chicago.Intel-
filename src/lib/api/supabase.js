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
/**
 * Building parcel data nearest a coordinate (within 100m).
 * Backed by RPC `find_building_at(lat, lng)` (003/005). Returns assessor-
 * sourced fields only — `tax_current`/`tax_annual` are null until the
 * treasurer connector lands; 311-derived counters and `flood_zone` come
 * from other pipelines and are not surfaced here yet.
 *
 * @returns {Promise<{
 *   pin: string, address: string, owner: string|null,
 *   year_built: number|null,
 *   purchase_year: number|null, purchase_price: number|null,
 *   school_elem: string|null, distance_m: number,
 *   source: { id: string, label: string, url: string },
 *   confidence: number,
 * } | null>}
 */
export async function getBuildingAt(lat, lng) {
  const rows = await rpc('find_building_at', { lat, lng });
  if (!rows || rows.length === 0) return null;
  const r = rows[0];
  return {
    pin: r.pin,
    address: r.address,
    owner: r.owner,
    year_built: r.year_built,
    purchase_year: r.purchase_year,
    purchase_price: r.purchase_price,
    school_elem: r.school_elem,
    distance_m: r.distance_m,
    source: {
      id: 'cook-county-assessor',
      label: 'Cook County Assessor',
      url: 'https://datacatalog.cookcountyil.gov/',
    },
    confidence: 9,
  };
}

/**
 * Latest successful pipeline_runs.completed_at for a source.
 * Backed by the per-source pipeline_runs row (migrations 005 + 011).
 * Returns null when no successful run exists yet (fresh deploy).
 *
 * @returns {Promise<string|null>} ISO timestamp or null
 */
export async function getLastSyncedAt(source) {
  if (!supabase) return null;
  const { data, error } = await supabase
    .from('pipeline_runs')
    .select('completed_at')
    .eq('source', source)
    .eq('status', 'success')
    .order('completed_at', { ascending: false })
    .limit(1)
    .maybeSingle();
  if (error) throw new DatabaseError({ cause: error, meta: { source } });
  return data?.completed_at ?? null;
}

/**
 * UDP Chicago displacement typology at a coordinate (tract-level spatial join).
 * Backed by RPC `displacement_at(lat, lng)` (020). Vintage 2013–2018 → 6/10.
 *
 * @returns {Promise<{
 *   geoid: string, typology: string,
 *   source: { id: string, label: string, url: string },
 *   confidence: number,
 * } | null>}
 */
export async function getDisplacementAt(lat, lng) {
  const rows = await rpc('displacement_at', { lat, lng });
  if (!rows || rows.length === 0) return null;
  const r = rows[0];
  return {
    geoid: r.geoid,
    typology: r.typology,
    source: {
      id: 'udp-chicago',
      label: 'Urban Displacement Project (UC Berkeley)',
      url: 'https://github.com/urban-displacement/displacement-typologies',
    },
    confidence: 6,
  };
}

export async function getCcaAt(lat, lng) {
  const rows = await rpc('cca_containing_point', { lat, lng });
  if (!rows || rows.length === 0) return null;
  return { id: rows[0].id, name: rows[0].name };
}

export async function getTractAt(lat, lng) {
  const rows = await rpc('tract_containing_point', { lat, lng });
  if (!rows || rows.length === 0) return null;
  return { id: rows[0].id, name: rows[0].name, cca_id: rows[0].cca_id };
}

export async function getCcaGeojson(ccaId) {
  const rows = await rpc('cca_geojson', { cca_id: ccaId });
  if (!rows || rows.length === 0) return null;
  return rows[0].cca_geojson ?? rows[0];
}

export async function getTractGeojson(geoid) {
  const rows = await rpc('tract_geojson', { geoid });
  if (!rows || rows.length === 0) return null;
  return rows[0].tract_geojson ?? rows[0];
}

export async function getCcaById(ccaId) {
  if (!supabase) return null;
  const { data, error } = await supabase
    .from('ccas')
    .select('id,name,rent_median,safety_score,walk_score,vibe_score,disp_score,data_vintage')
    .eq('id', ccaId)
    .single();
  if (error) throw new DatabaseError({ cause: error, meta: { ccaId } });
  return data;
}

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
