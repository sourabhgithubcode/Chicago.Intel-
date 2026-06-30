// Mapbox Directions — on-demand route line from the building to an amenity, for
// the amenity route overlay. The token is already in the browser (the map uses
// it), so this is a direct client call — no treasurer round-trip. Cached
// in-memory per from|to|profile so re-hovering a row is instant.
// Caller: MapView.jsx (amenity route overlay).

const TOKEN = import.meta.env.VITE_MAPBOX_TOKEN;
const _cache = new Map();

/**
 * Route between two {lat, lng} points. profile = 'walking' | 'driving'.
 * Returns { geometry (GeoJSON LineString), distance_m, duration_s } or null.
 */
export async function getRoute(from, to, profile = 'walking') {
  if (!TOKEN || !from || !to || from.lat == null || to.lat == null) return null;
  const key = `${profile}|${from.lng.toFixed(5)},${from.lat.toFixed(5)}|${to.lng.toFixed(5)},${to.lat.toFixed(5)}`;
  if (_cache.has(key)) return _cache.get(key);
  const url =
    `https://api.mapbox.com/directions/v5/mapbox/${profile}` +
    `/${from.lng},${from.lat};${to.lng},${to.lat}` +
    `?geometries=geojson&overview=full&access_token=${TOKEN}`;
  let out = null;
  try {
    const res = await fetch(url);
    if (res.ok) {
      const r = (await res.json()).routes?.[0];
      if (r) out = { geometry: r.geometry, distance_m: r.distance, duration_s: r.duration };
    }
  } catch { /* network / token — no route, fall through to null */ }
  _cache.set(key, out);
  return out;
}
