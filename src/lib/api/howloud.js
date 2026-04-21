// API #12 — HowLoud (Tier 4, optional paid, V3+)
// Noise score per coordinate. Env: VITE_HOWLOUD_KEY
// Cost: $0.05/query or $99/mo unlimited.

import { ExternalApiError } from '../errors/index.js';
import { withRetry, CircuitBreaker } from '../retry/index.js';

const KEY = import.meta.env.VITE_HOWLOUD_KEY;
const breaker = new CircuitBreaker({ name: 'howloud' });

export const enabled = Boolean(KEY);

export async function noiseAt({ lat, lng }) {
  if (!enabled) return null;
  return breaker.fire(() =>
    withRetry(async () => {
      // TODO: wire up to HowLoud endpoint when key is added. Until then,
      // fallback is CDOT traffic volume proxy in calculations/noiseProxy.js.
      const res = await fetch(
        `https://api.howloud.com/score?lat=${lat}&lng=${lng}&key=${KEY}`
      );
      if (!res.ok) throw new ExternalApiError({ meta: { status: res.status } });
      return res.json();
    })
  );
}
