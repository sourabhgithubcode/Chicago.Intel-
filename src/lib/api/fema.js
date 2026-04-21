// API #5 — FEMA NFHL (Tier 2, free, no key)
// Flood zone per coordinate. Free + generous rate limits.
// Failure mode: "Unknown" in UI. Low impact.

import { ExternalApiError } from '../errors/index.js';
import { withRetry, CircuitBreaker } from '../retry/index.js';

const BASE =
  'https://hazards.fema.gov/gis/nfhl/rest/services/public/NFHL/MapServer/28/query';
const breaker = new CircuitBreaker({ name: 'fema' });

export async function floodZoneAt({ lat, lng }) {
  return breaker.fire(() =>
    withRetry(async () => {
      const params = new URLSearchParams({
        f: 'json',
        geometry: `${lng},${lat}`,
        geometryType: 'esriGeometryPoint',
        inSR: '4326',
        spatialRel: 'esriSpatialRelIntersects',
        outFields: 'FLD_ZONE,ZONE_SUBTY',
        returnGeometry: 'false',
      });
      const res = await fetch(`${BASE}?${params}`);
      const json = await res.json();
      if (!res.ok) throw new ExternalApiError({ meta: { status: res.status } });
      const f = json.features?.[0]?.attributes;
      return f
        ? { zone: f.FLD_ZONE, subtype: f.ZONE_SUBTY ?? null }
        : { zone: 'X', subtype: null };
    })
  );
}
