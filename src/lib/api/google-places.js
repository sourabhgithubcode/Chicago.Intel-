// API #4 — Google Places (Tier 2, required for V2 amenities)
// Nearby search + price_level signal. Env: VITE_GOOGLE_PLACES_KEY
// Cost: Nearby $32/1K, Details $17/1K. $200 credit covers ~6K Nearby.
// CRITICAL: cache per-address for 30 days in Supabase amenities_cache table
// (this in-memory cache is a second-layer safeguard only).

import { ExternalApiError } from '../errors/index.js';
import { withRetry, CircuitBreaker } from '../retry/index.js';
import { amenityCache } from '../cache/index.js';

const KEY = import.meta.env.VITE_GOOGLE_PLACES_KEY;
const breaker = new CircuitBreaker({ name: 'google-places' });

export async function nearbySearch({ lat, lng, type, radiusMeters = 402 }) {
  const key = `${type}:${lat.toFixed(4)},${lng.toFixed(4)}:${radiusMeters}`;
  const cached = amenityCache.get(key);
  if (cached) return cached;

  const data = await breaker.fire(() =>
    withRetry(async () => {
      // TODO: migrate to Places API (New) v1 when Edge Function proxy is live —
      // this endpoint needs server-side CORS.
      const url = `https://maps.googleapis.com/maps/api/place/nearbysearch/json?location=${lat},${lng}&radius=${radiusMeters}&type=${type}&key=${KEY}`;
      const res = await fetch(url);
      const json = await res.json();
      if (json.status !== 'OK' && json.status !== 'ZERO_RESULTS') {
        throw new ExternalApiError({ meta: { status: json.status } });
      }
      return json.results ?? [];
    })
  );

  amenityCache.set(key, data);
  return data;
}
