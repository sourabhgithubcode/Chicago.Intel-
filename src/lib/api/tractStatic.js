// Static tract fallback bundle (lazy-loaded). Same rationale as ccaStatic.js:
// when the anon SELECT policy on `tracts` (migration 026) is unapplied, the tract
// breadcrumb, the map tract layer, and the building-view DisplacementRisk section
// (displacement_at joins tracts) all go blank. Each feature carries {id, cca_id,
// typology} so all three live calls have a fallback. Regenerate with
// scripts/scoring/export_tract_static.py.

import { booleanPointInPolygon, point } from '@turf/turf';

let _fc = null;
async function load() {
  if (!_fc) _fc = (await import('../../data/tracts.json')).default;
  return _fc;
}

async function containing(lat, lng) {
  const fc = await load();
  const pt = point([lng, lat]);
  return fc.features.find((feat) => booleanPointInPolygon(pt, feat)) ?? null;
}

/** {id, name, cca_id} of the tract containing (lat,lng), or null. */
export async function tractContaining(lat, lng) {
  const f = await containing(lat, lng);
  return f ? { id: f.properties.id, name: null, cca_id: f.properties.cca_id } : null;
}

/** GeoJSON geometry for one tract geoid, or null. */
export async function tractGeometry(geoid) {
  const fc = await load();
  const f = fc.features.find((feat) => feat.properties.id === geoid);
  return f ? f.geometry : null;
}

/** {geoid, typology} for the tract containing (lat,lng), or null. */
export async function displacementContaining(lat, lng) {
  const f = await containing(lat, lng);
  if (!f || !f.properties.typology) return null;
  return { geoid: f.properties.id, typology: f.properties.typology };
}
