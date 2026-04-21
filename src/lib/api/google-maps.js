// API #2 — Google Maps Geocoding (Tier 1, required)
// Address → lat/lng. Env: VITE_GOOGLE_MAPS_KEY (HTTP-referrer restricted)
// Cost: ~28K free/mo via $200 credit. Cache 24hr (geocodeCache).

import { GeocodeError, OutOfBoundsError } from '../errors/index.js';
import { withRetry, CircuitBreaker } from '../retry/index.js';
import { geocodeCache } from '../cache/index.js';
import { validateAddress, validateChicagoBounds } from '../validation/index.js';

const KEY = import.meta.env.VITE_GOOGLE_MAPS_KEY;
const breaker = new CircuitBreaker({ name: 'google-maps' });

export async function geocode(rawAddress) {
  const address = validateAddress(rawAddress);
  const cached = geocodeCache.get(address);
  if (cached) return cached;

  const result = await breaker.fire(() =>
    withRetry(async () => {
      const url = `https://maps.googleapis.com/maps/api/geocode/json?address=${encodeURIComponent(address)}&key=${KEY}&components=locality:Chicago|administrative_area:IL`;
      const res = await fetch(url);
      const json = await res.json();
      if (json.status !== 'OK' || !json.results?.length) {
        throw new GeocodeError({ meta: { address, status: json.status } });
      }
      const { lat, lng } = json.results[0].geometry.location;
      return { lat, lng, formatted: json.results[0].formatted_address };
    })
  );

  validateChicagoBounds(result);
  geocodeCache.set(address, result);
  return result;
}
