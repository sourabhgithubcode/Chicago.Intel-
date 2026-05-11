// API — Cook County Treasurer per-PIN tax lookup.
// Backed by the Flask service on Render (was a Supabase Edge Function — Deno's
// strict TLS rejected CCT's misconfigured cert chain). Confidence 9/10 — the
// source is the official Treasurer site; brief upstream outages possible.
//
// Env: VITE_TREASURER_API_URL (e.g. https://chicago-intel-treasurer.onrender.com)

import { DatabaseError } from '../errors/index.js';

const SOURCE = {
  id: 'cook-county-treasurer',
  label: 'Cook County Treasurer',
  url: 'https://www.cookcountytreasurer.com/',
};

const API = import.meta.env.VITE_TREASURER_API_URL;

/**
 * Live Treasurer lookup for a 14-digit PIN (no dashes).
 * Returns null when no pin is passed. Throws DatabaseError on failure.
 *
 * @returns {Promise<{
 *   tax_year: number|null,
 *   total_billed: number|null,
 *   total_paid: number|null,
 *   amount_due: number|null,
 *   fetched_at: string,
 *   cached: boolean,
 *   source: { id: string, label: string, url: string },
 *   confidence: number,
 * } | null>}
 */
export async function getTreasurerData(pin) {
  if (!pin) return null;
  if (!API) throw new DatabaseError({ meta: { reason: 'no-treasurer-url' } });

  const clean = String(pin).replace(/\D/g, '');
  if (!/^\d{14}$/.test(clean)) {
    throw new DatabaseError({
      meta: { reason: 'invalid-pin', pin: String(pin) },
    });
  }

  let res;
  try {
    res = await fetch(`${API}/treasurer-lookup`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pin: clean }),
    });
  } catch (cause) {
    throw new DatabaseError({ cause, meta: { pin: clean, reason: 'network' } });
  }
  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new DatabaseError({
      meta: { pin: clean, status: res.status, detail: detail.slice(0, 200) },
    });
  }
  const data = await res.json();
  if (data.error) {
    throw new DatabaseError({
      meta: { pin: clean, detail: data.detail ?? data.error },
    });
  }

  return {
    tax_year: data.tax_year ?? null,
    total_billed: data.total_billed ?? null,
    total_paid: data.total_paid ?? null,
    amount_due: data.amount_due ?? null,
    fetched_at: data.fetched_at,
    cached: !!data.cached,
    source: SOURCE,
    confidence: 9,
  };
}
