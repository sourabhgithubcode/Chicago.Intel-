// API #15 — Illinois Report Card (Tier 4, free, V3+ opportunity index)
// Per-school ratings, demographics, test scores.
// Docs: illinoisreportcard.com — request access pattern TBD.

import { ExternalApiError } from '../errors/index.js';
import { withRetry, CircuitBreaker } from '../retry/index.js';

const breaker = new CircuitBreaker({ name: 'ilrc' });

export async function schoolRating({ rcdtsCode }) {
  return breaker.fire(() =>
    withRetry(async () => {
      // TODO: resolve the exact endpoint once API access is confirmed.
      const res = await fetch(
        `https://illinoisreportcard.com/api/school/${rcdtsCode}`
      );
      if (!res.ok) throw new ExternalApiError({ meta: { status: res.status } });
      return res.json();
    })
  );
}
