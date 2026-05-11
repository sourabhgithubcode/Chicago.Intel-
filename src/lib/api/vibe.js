// Foursquare Places v4 — nearby vibe / lifestyle POIs. 30d cache.
// Backed by /vibe on the Render Flask service.
// Replaces Yelp (expired trial + restrictive caching TOS).
// Caller: future Vibe section in BuildingDetail.

const API = import.meta.env.VITE_TREASURER_API_URL;

const SOURCE = {
  id: 'foursquare',
  label: 'Foursquare Places',
  url: 'https://docs.foursquare.com/developer/reference/places-api',
};

export async function getVibe(lat, lng) {
  if (lat == null || lng == null) return null;
  if (!API) throw new Error('VITE_TREASURER_API_URL not set');

  const res = await fetch(`${API}/vibe?lat=${lat}&lng=${lng}`);
  if (!res.ok) throw new Error(`Vibe HTTP ${res.status}`);
  const data = await res.json();
  if (data.error) return null;
  return {
    places: data.places ?? [],
    cached: !!data.cached,
    source: SOURCE,
    confidence: 7,
  };
}
