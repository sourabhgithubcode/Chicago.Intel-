// Google Maps Geocoding — address string → {lat, lng, formatted_address}.
// Env: VITE_GOOGLE_MAPS_KEY (must be domain-restricted in Google Cloud).
// Caller: SearchBar.jsx.

const KEY = import.meta.env.VITE_GOOGLE_MAPS_KEY;

const CHICAGO_BOUNDS = '41.644,-87.940|42.023,-87.524';

export async function geocodeAddress(query) {
  if (!KEY) throw new Error('VITE_GOOGLE_MAPS_KEY not set');
  if (!query || !query.trim()) return null;

  const params = new URLSearchParams({
    address: query,
    bounds: CHICAGO_BOUNDS,
    components: 'locality:Chicago|administrative_area:IL|country:US',
    key: KEY,
  });
  const res = await fetch(
    `https://maps.googleapis.com/maps/api/geocode/json?${params}`
  );
  if (!res.ok) throw new Error(`Geocode HTTP ${res.status}`);
  const body = await res.json();
  if (body.status === 'ZERO_RESULTS') return null;
  if (body.status !== 'OK') {
    throw new Error(`Geocode ${body.status}: ${body.error_message ?? ''}`);
  }
  const top = body.results[0];
  return {
    lat: top.geometry.location.lat,
    lng: top.geometry.location.lng,
    formatted_address: top.formatted_address,
  };
}
