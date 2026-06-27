// Static CCA fallback bundle (lazy-loaded).
//
// The frontend uses the anon key; if the anon SELECT policy on `ccas` is not yet
// applied (migration 026), every live CCA query returns 0 rows and the CCA card,
// breadcrumb, and map CCA layer go blank. CCA scores are slow-changing reference
// data (ACS 5-yr rent, 5-yr CPD safety, static 2018 UDP, infrastructure walk), so
// a bundled snapshot of the REAL computed values is an acceptable fallback.
//
// FALLBACK ONLY: the live DB query is always tried first, so once 026 is applied
// the live data wins and this bundle is never loaded (it's a separate lazy chunk,
// so it adds nothing to the main bundle). Regenerate after recomputing scores with
// scripts/scoring/export_cca_static.py.

import { booleanPointInPolygon, point } from '@turf/turf';

let _fc = null;
async function load() {
  if (!_fc) _fc = (await import('../../data/ccas.json')).default;
  return _fc;
}

/** Scores for one CCA (same shape as getCcaById's select), or null. */
export async function ccaById(id) {
  const fc = await load();
  const f = fc.features.find((feat) => feat.properties.id === Number(id));
  return f ? { ...f.properties } : null;
}

/** {id, name} of the CCA whose polygon contains (lat,lng), or null. */
export async function ccaContaining(lat, lng) {
  const fc = await load();
  const pt = point([lng, lat]);
  const f = fc.features.find((feat) => booleanPointInPolygon(pt, feat));
  return f ? { id: f.properties.id, name: f.properties.name } : null;
}

/** GeoJSON geometry for one CCA, or null. */
export async function ccaGeometry(id) {
  const fc = await load();
  const f = fc.features.find((feat) => feat.properties.id === Number(id));
  return f ? f.geometry : null;
}
