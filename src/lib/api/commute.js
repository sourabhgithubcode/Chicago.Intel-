// Mapbox Directions — building → user-saved work destination. 30d cache.
// Backed by /commute on the Render Flask service.
// Caller: future Commute section in BuildingDetail (after user saves a
// work address). Origin is always the current building's PIN.
//
// Free tier 100K req/mo. Cached 30d — captures long-term-average commute,
// not real-time traffic conditions.

const API = import.meta.env.VITE_TREASURER_API_URL;

const SOURCE = {
  id: 'mapbox-directions',
  label: 'Mapbox Directions',
  url: 'https://docs.mapbox.com/api/navigation/directions/',
};

export async function getCommute({ pin, from, work, mode = 'driving-traffic' }) {
  if (!pin || !from || !work) return null;
  if (!API) throw new Error('VITE_TREASURER_API_URL not set');
  const params = new URLSearchParams({
    pin: String(pin).replace(/\D/g, ''),
    from_lat: String(from.lat),
    from_lng: String(from.lng),
    work_lat: String(work.lat),
    work_lng: String(work.lng),
    mode,
  });
  const res = await fetch(`${API}/commute?${params}`);
  if (!res.ok) throw new Error(`Commute HTTP ${res.status}`);
  const data = await res.json();
  if (data.error) return null;
  return {
    minutes: data.minutes,
    distance_m: data.distance_m,
    mode: data.mode,
    fetched_at: data.fetched_at,
    cached: !!data.cached,
    source: SOURCE,
    confidence: 8,
  };
}
