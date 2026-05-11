// US Census Bureau Geocoder, proxied through our Render Flask service.
// Census doesn't return CORS headers, so browsers can't call it directly —
// the proxy re-emits the same response with CORS allowed.
// Caller: SearchBar.jsx.

const API = import.meta.env.VITE_TREASURER_API_URL;

const CHI_BBOX = {
  west: -87.940, east: -87.524,
  south: 41.644, north: 42.023,
};

function inChicagoBbox(x, y) {
  return (
    x >= CHI_BBOX.west && x <= CHI_BBOX.east &&
    y >= CHI_BBOX.south && y <= CHI_BBOX.north
  );
}

export async function geocodeAddress(query) {
  if (!query || !query.trim()) return null;
  if (!API) throw new Error('VITE_TREASURER_API_URL not set');

  const res = await fetch(`${API}/geocode?q=${encodeURIComponent(query)}`);
  if (!res.ok) throw new Error(`Geocode HTTP ${res.status}`);
  const body = await res.json();
  const matches = body?.result?.addressMatches ?? [];
  if (matches.length === 0) return null;

  const chiMatch = matches.find((m) =>
    inChicagoBbox(m.coordinates?.x, m.coordinates?.y)
  );
  const top = chiMatch ?? matches[0];

  return {
    lat: top.coordinates.y,
    lng: top.coordinates.x,
    formatted_address: top.matchedAddress,
  };
}
