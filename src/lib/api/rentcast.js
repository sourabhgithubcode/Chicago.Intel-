// API #11 — Rentcast (Tier 4, optional paid, V3+)
// Live market rent per address. Env: VITE_RENTCAST_KEY
// Cost: $49/mo for 3K calls.
// Current behavior: disabled unless key present — fall back to user-entered rent.

import { ExternalApiError } from '../errors/index.js';
import { withRetry, CircuitBreaker } from '../retry/index.js';

const KEY = import.meta.env.VITE_RENTCAST_KEY;
const breaker = new CircuitBreaker({ name: 'rentcast' });

export const enabled = Boolean(KEY);

export async function estimateRent({ address }) {
  if (!enabled) return null;
  return breaker.fire(() =>
    withRetry(async () => {
      // TODO: implement when VITE_RENTCAST_KEY is provisioned in V3.
      const res = await fetch(
        `https://api.rentcast.io/v1/avm/rent/long-term?address=${encodeURIComponent(address)}`,
        { headers: { 'X-Api-Key': KEY } }
      );
      if (!res.ok) throw new ExternalApiError({ meta: { status: res.status } });
      return res.json();
    })
  );
}
