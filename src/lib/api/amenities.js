// Google Places Nearby Search by lat/lng + category. 30d cache.
// Backed by /amenities on the Render Flask service.
// Caller: future Amenities section in BuildingDetail.
//
// Free tier: $200/mo Google credit, ~10K nearby-search calls. Aggressive
// caching softens the cost; categories are limited to the 8 we currently
// surface (grocery, gym, pharmacy, coffee, restaurant, park, bank, laundry).

import { cachedJSON } from './cache.js';

const API = import.meta.env.VITE_TREASURER_API_URL;

// Server caches per address 30d; a 7d client cache is safe and, on a repeat
// view, skips the network entirely — crucial when the free-tier treasurer is
// asleep (~30s cold start).
const AMENITIES_TTL_MS = 7 * 24 * 60 * 60 * 1000;

const SOURCE = {
  id: 'google-places',
  label: 'Google Places',
  url: 'https://developers.google.com/maps/documentation/places/web-service',
};

// All categories in ONE request (the /amenities_all batch endpoint) — avoids 13
// serialized round-trips through the single-worker treasurer service.
// Returns { category: [{ name, distance_m }] } or null. Caller: amenityScore.js.
export async function getAmenitiesAll(lat, lng) {
  if (lat == null || lng == null || !API) return null;
  const key = `ci.am:${lat.toFixed(4)},${lng.toFixed(4)}`;
  return cachedJSON(key, AMENITIES_TTL_MS, async () => {
    const res = await fetch(`${API}/amenities_all?lat=${lat}&lng=${lng}`);
    if (!res.ok) throw new Error(`Amenities HTTP ${res.status}`);
    const data = await res.json();
    if (data.error) return null;
    return data.categories ?? null;
  }, (d) => d && Object.keys(d).length > 0);
}

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
