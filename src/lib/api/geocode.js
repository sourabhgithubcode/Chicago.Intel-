// US Census Bureau Geocoder — free, no key, US-only, accurate for Chicago.
// https://geocoding.geo.census.gov/
// Caller: SearchBar.jsx.
//
// Returns null on no match. Throws on transport/HTTP errors.

const ENDPOINT =
  'https://geocoding.geo.census.gov/geocoder/locations/onelineaddress';

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

  // Append "Chicago IL" if the user didn't include it — the Census geocoder
  // is nationwide and would otherwise rank matches by other factors.
  const q = /chicago/i.test(query) ? query : `${query}, Chicago, IL`;

  const params = new URLSearchParams({
    address: q,
    benchmark: 'Public_AR_Current',
    format: 'json',
  });
  const res = await fetch(`${ENDPOINT}?${params}`);
  if (!res.ok) throw new Error(`Geocode HTTP ${res.status}`);
  const body = await res.json();
  const matches = body?.result?.addressMatches ?? [];
  if (matches.length === 0) return null;

  // Prefer a match inside Chicago's bbox if one exists (the geocoder
  // sometimes returns a same-named address in a suburb first).
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
