// Google Places Nearby Search by lat/lng + category. 30d cache.
// Backed by /amenities on the Render Flask service.
// Caller: future Amenities section in BuildingDetail.
//
// Free tier: $200/mo Google credit, ~10K nearby-search calls. Aggressive
// caching softens the cost; categories are limited to the 8 we currently
// surface (grocery, gym, pharmacy, coffee, restaurant, park, bank, laundry).

const API = import.meta.env.VITE_TREASURER_API_URL;

const SOURCE = {
  id: 'google-places',
  label: 'Google Places',
  url: 'https://developers.google.com/maps/documentation/places/web-service',
};

export async function getAmenities(lat, lng, category) {
  if (lat == null || lng == null || !category) return null;
  if (!API) throw new Error('VITE_TREASURER_API_URL not set');

  const res = await fetch(
    `${API}/amenities?lat=${lat}&lng=${lng}&category=${encodeURIComponent(category)}`
  );
  if (!res.ok) throw new Error(`Amenities HTTP ${res.status}`);
  const data = await res.json();
  if (data.error) return null;
  return {
    category: data.category,
    places: data.places ?? [],
    cached: !!data.cached,
    source: SOURCE,
    confidence: 7,
  };
}
