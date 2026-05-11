// FEMA NFHL flood zone per-coordinate lookup.
// Backed by /flood-zone on the Render Flask service (cached 1yr).
// Caller: future Flood section in BuildingDetail.
//
// FEMA flood zones reference:
//   X   — minimal hazard, outside FIRM-mapped area
//   A   — 1% annual chance flood, no base elevation determined
//   AE  — 1% annual chance flood, base flood elevation determined
//   AH/AO — shallow flooding areas
//   V/VE — coastal high-velocity hazard

const API = import.meta.env.VITE_TREASURER_API_URL;

const SOURCE = {
  id: 'fema-nfhl',
  label: 'FEMA NFHL',
  url: 'https://hazards.fema.gov/femaportal/NFHL/',
};

export async function getFloodZone(lat, lng) {
  if (lat == null || lng == null) return null;
  if (!API) throw new Error('VITE_TREASURER_API_URL not set');

  const res = await fetch(`${API}/flood-zone?lat=${lat}&lng=${lng}`);
  if (!res.ok) {
    throw new Error(`FEMA HTTP ${res.status}`);
  }
  const data = await res.json();
  return {
    flood_zone: data.flood_zone ?? null,
    zone_subtype: data.zone_subtype ?? null,
    fetched_at: data.fetched_at,
    cached: !!data.cached,
    source: SOURCE,
    confidence: 9,
  };
}
