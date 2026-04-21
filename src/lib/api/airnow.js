// API #13 — EPA AirNow (Tier 4, free with key, V3+)
// Air quality (AQI) by zip. Rate limit: 500 req/hr.
// Key request: docs.airnowapi.org. Env: VITE_AIRNOW_KEY

import { ExternalApiError } from '../errors/index.js';
import { withRetry, CircuitBreaker } from '../retry/index.js';

const KEY = import.meta.env.VITE_AIRNOW_KEY;
const breaker = new CircuitBreaker({ name: 'airnow' });

export const enabled = Boolean(KEY);

export async function aqiByZip(zip) {
  if (!enabled) return null;
  return breaker.fire(() =>
    withRetry(async () => {
      const res = await fetch(
        `https://www.airnowapi.org/aq/observation/zipCode/current/?format=application/json&zipCode=${zip}&API_KEY=${KEY}`
      );
      if (!res.ok) throw new ExternalApiError({ meta: { status: res.status } });
      return res.json();
    })
  );
}
