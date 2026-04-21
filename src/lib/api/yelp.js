// API #16 — Yelp Fusion (Tier 4, free 500/day, V3+)
// Restaurants, ratings, vibe. Env: VITE_YELP_KEY
// Known issue: documented North Side bias — confidence capped at 6/10 in
// calculations/confidence.js. Prefer Google Places as primary, Yelp as enrichment.

import { ExternalApiError } from '../errors/index.js';
import { withRetry, CircuitBreaker } from '../retry/index.js';

const KEY = import.meta.env.VITE_YELP_KEY;
const breaker = new CircuitBreaker({ name: 'yelp' });

export const enabled = Boolean(KEY);

export async function searchBusinesses({ lat, lng, term, radiusMeters = 402 }) {
  if (!enabled) return null;
  return breaker.fire(() =>
    withRetry(async () => {
      const url = `https://api.yelp.com/v3/businesses/search?latitude=${lat}&longitude=${lng}&term=${encodeURIComponent(term)}&radius=${radiusMeters}`;
      const res = await fetch(url, {
        headers: { Authorization: `Bearer ${KEY}` },
      });
      if (!res.ok) throw new ExternalApiError({ meta: { status: res.status } });
      return res.json();
    })
  );
}
