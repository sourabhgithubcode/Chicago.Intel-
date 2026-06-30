// API #1 — Supabase (Tier 1, required)
// Database + auto REST + RPC. Env: VITE_SUPABASE_URL, VITE_SUPABASE_ANON_KEY
// Failure mode: entire app down. Mitigation: retry + circuit breaker.

import { createClient } from '@supabase/supabase-js';
import { DatabaseError } from '../errors/index.js';
import { withRetry, CircuitBreaker } from '../retry/index.js';
import { ccaById, ccaContaining, ccaGeometry } from './ccaStatic.js';
import { tractContaining, tractGeometry, displacementContaining } from './tractStatic.js';
import { tractLabel } from '../formatters/index.js';

const url = import.meta.env.VITE_SUPABASE_URL;
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

export const supabase = url && anonKey ? createClient(url, anonKey) : null;

const breaker = new CircuitBreaker({ name: 'supabase' });

export async function rpc(name, params = {}) {
  if (!supabase) throw new DatabaseError({ meta: { reason: 'no-client' } });
  return breaker.fire(() =>
    // find_building_at is a spatial query that flakily exceeds the anon role's
    // 3s statement_timeout (missing geography GIST index — see WORKLOG/026/index
    // fix). withRetry sits INSIDE breaker.fire, so a whole retry sequence is one
    // breaker failure; extra attempts buy reliability without tripping the circuit.
    withRetry(async () => {
      const { data, error } = await supabase.rpc(name, params);
      if (error) throw new DatabaseError({ cause: error, meta: { name, params } });
      return data;
    }, { attempts: 5, baseMs: 300 })
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
const BUILDING_COLS =
  'pin,address,owner,year_built,purchase_year,purchase_price,tax_current,tax_annual,' +
  'violations_5yr,bug_reports,heat_complaints,landlord_score,flood_zone,school_elem';

function shapeBuilding(r, distance_m) {
  return {
    ...r,
    distance_m: distance_m ?? r.distance_m ?? 0,
    source: {
      id: 'cook-county-assessor',
      label: 'Cook County Assessor',
      url: 'https://datacatalog.cookcountyil.gov/',
    },
    confidence: 9,
  };
}

export async function getBuildingAt(lat, lng, address) {
  // Fast path: exact address match. address_norm is indexed (~0.2s), so this
  // avoids the spatial find_building_at RPC, which flakily exceeds the anon
  // role's 3s statement_timeout (geometry/geography GIST index not used).
  if (supabase && address) {
    const norm = address.split(',')[0].trim().toUpperCase().replace(/\s+/g, ' ');
    if (norm && !/\(default\)/i.test(norm)) {
      const { data } = await supabase
        .from('buildings').select(BUILDING_COLS)
        .eq('address_norm', norm).limit(1).maybeSingle();
      if (data) return shapeBuilding(data, 0);
    }
  }
  // Fallback: nearest building within 100 m (spatial RPC).
  const rows = await rpc('find_building_at', { lat, lng });
  if (!rows || rows.length === 0) return null;
  return shapeBuilding(rows[0]);
}

/**
 * Exact building-footprint polygon nearest a coordinate (within 60 m), as
 * GeoJSON geometry. Backed by RPC `building_footprint_at(lat, lng)` (029).
 * Returns null when no footprint is close (MapView then falls back to the
 * Mapbox tile footprint / circle).
 *
 * @returns {Promise<object|null>} GeoJSON geometry or null
 */
export async function getBuildingFootprint(lat, lng) {
  // Best-effort + optional: call directly (single attempt, no retry/breaker) so
  // it fails fast and MapView falls back to the tile/circle instantly when the
  // RPC is slow or absent (e.g. migration 029 not yet applied).
  if (!supabase) return null;
  try {
    const { data, error } = await supabase.rpc('building_footprint_at', { lat, lng });
    if (error) return null;
    if (data && typeof data === 'object' && data.type) return data; // scalar RETURNS JSON
  } catch { /* fall back to tile/circle in MapView */ }
  return null;
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
  let r = null;
  try {
    const rows = await rpc('displacement_at', { lat, lng });
    if (rows && rows.length > 0) r = rows[0];
  } catch { /* fall through to static bundle */ }
  if (!r) r = await displacementContaining(lat, lng); // fallback while RLS (026) unapplied
  if (!r) return null;
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
  try {
    const rows = await rpc('cca_containing_point', { lat, lng });
    if (rows && rows.length > 0) return { id: rows[0].id, name: rows[0].name };
  } catch { /* fall through to static bundle */ }
  return ccaContaining(lat, lng); // fallback while anon RLS (migration 026) unapplied
}

export async function getTractAt(lat, lng) {
  try {
    const rows = await rpc('tract_containing_point', { lat, lng });
    if (rows && rows.length > 0) {
      return { id: rows[0].id, name: rows[0].name, cca_id: rows[0].cca_id };
    }
  } catch { /* fall through to static bundle */ }
  return tractContaining(lat, lng); // fallback while RLS (026) unapplied
}

export async function getCcaGeojson(ccaId) {
  try {
    const rows = await rpc('cca_geojson', { cca_id: ccaId });
    if (rows && rows.length > 0) return rows[0].cca_geojson ?? rows[0];
  } catch { /* fall through to static bundle */ }
  return ccaGeometry(ccaId); // fallback while anon RLS (migration 026) unapplied
}

export async function getTractGeojson(geoid) {
  try {
    const rows = await rpc('tract_geojson', { geoid });
    if (rows && rows.length > 0) return rows[0].tract_geojson ?? rows[0];
  } catch { /* fall through to static bundle */ }
  return tractGeometry(geoid); // fallback while RLS (026) unapplied
}

export async function getCcaById(ccaId) {
  if (supabase) {
    const { data, error } = await supabase
      .from('ccas')
      .select('id,name,rent_median,safety_score,walk_score,vibe_score,disp_score,data_vintage,'
        + 'composite_score,afford_score,vuln_score,bike_score,run_score,'
        + 'housing_cost_mo,transport_cost_mo,income_median,poverty_rate,vacancy_rate,'
        + 'renter_occupied_pct,transit_share,autos_per_hh')
      .eq('id', ccaId)
      .maybeSingle();
    if (!error && data) return data;
    // error or 0 rows (anon RLS, migration 026 unapplied) → static bundle below
  }
  return ccaById(ccaId);
}

/**
 * All 77 CCAs with their engine scores, for the map "color by" choropleth.
 * Anon SELECT via migration 026. Memoized for the session.
 * Caller: MapView.jsx (city level). Returns [] if unavailable (map stays flat).
 */
let _ccaScores;
export async function getCcaScores() {
  if (_ccaScores !== undefined) return _ccaScores;
  if (!supabase) return (_ccaScores = []);
  const { data, error } = await supabase
    .from('ccas')
    .select('id,composite_score,afford_score,vuln_score,safety_score,walk_score,'
      + 'disp_score,vibe_score,bike_score,run_score');
  _ccaScores = !error && data ? data : [];
  return _ccaScores;
}

/**
 * All ~1300 tracts with their engine scores, for the neighborhood-level granular
 * choropleth. Paged (PostgREST caps a response at 1000 rows). Memoized.
 * Caller: MapView.jsx. Returns [] if unavailable (columns/migration 031 absent).
 */
let _tractScores;
export async function getTractScores() {
  if (_tractScores !== undefined) return _tractScores;
  if (!supabase) return (_tractScores = []);
  const cols = 'id,composite_score,afford_score,vuln_score,safety_score,walk_score,'
    + 'disp_score,vibe_score,bike_score,run_score';
  const rows = [];
  for (let from = 0; ; from += 1000) {
    const { data, error } = await supabase.from('tracts').select(cols).range(from, from + 999);
    if (error) return (_tractScores = rows);          // partial/none → what we have
    rows.push(...data);
    if (data.length < 1000) break;                    // last page
  }
  return (_tractScores = rows);
}

/**
 * Buildings within a tract (migration 032 RPC) as a points FeatureCollection,
 * for the tract-level building choropleth. Each feature carries the building
 * metrics (violations_5yr / heat_complaints / bug_reports / year_built).
 * Caller: MapView.jsx. Returns an empty collection if unavailable.
 */
export async function getBuildingsInTract(geoid) {
  const empty = { type: 'FeatureCollection', features: [] };
  if (!supabase || geoid == null) return empty;
  let rows;
  try {
    rows = await rpc('buildings_in_tract', { p_geoid: geoid });
  } catch {
    return empty;
  }
  return {
    type: 'FeatureCollection',
    features: (rows || []).map((r) => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [r.lng, r.lat] },
      properties: {
        pin: r.pin,
        violations_5yr: r.violations_5yr,
        heat_complaints: r.heat_complaints,
        bug_reports: r.bug_reports,
        year_built: r.year_built,
      },
    })),
  };
}

/**
 * Census-tract scores (the tract's OWN values, not its CCA's). Backed by the
 * tracts table (anon SELECT via migration 026). safety/walk are ~59% filled;
 * rent/displacement ~96%. Caller: AreaScores.jsx (tract level).
 */
export async function getTractById(geoid) {
  if (!supabase || geoid == null) return null;
  const { data, error } = await supabase
    .from('tracts')
    .select('id,name,rent_median,safety_score,walk_score,disp_score,data_vintage')
    .eq('id', geoid)
    .maybeSingle();
  if (!error && data) return { ...data, name: data.name || tractLabel(geoid) };
  return null;
}

/**
 * Citywide aggregate across the 77 Community Areas — median of CCA median rents,
 * mean of the CCA scores. A rough citywide signal (aggregate of aggregates).
 * Memoized for the session. Caller: AreaScores.jsx (city level).
 */
let _cityScores;
export async function getCityScores() {
  if (_cityScores !== undefined) return _cityScores;
  if (!supabase) return (_cityScores = null);
  const { data } = await supabase
    .from('ccas')
    .select('rent_median,safety_score,walk_score,disp_score,afford_score,vuln_score,composite_score');
  if (!data?.length) return (_cityScores = null);
  const median = (xs) => {
    const s = xs.filter((x) => x != null).sort((a, b) => a - b);
    return s.length ? s[Math.floor(s.length / 2)] : null;
  };
  const mean = (k) => {
    const v = data.map((r) => r[k]).filter((x) => x != null);
    return v.length ? +(v.reduce((a, b) => a + b, 0) / v.length).toFixed(1) : null;
  };
  _cityScores = {
    name: 'Chicago',
    rent_median: median(data.map((r) => r.rent_median)),
    safety_score: mean('safety_score'),
    walk_score: mean('walk_score'),
    disp_score: mean('disp_score'),
    afford_score: mean('afford_score'),
    vuln_score: mean('vuln_score'),
    composite_score: mean('composite_score'),
    data_vintage: '2019–23',
  };
  return _cityScores;
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
