// API — Cook County Treasurer per-PIN tax lookup.
// Backed by the `treasurer-lookup` Edge Function (live scrape + 30d cache).
// Confidence 9/10 — the source is the official Treasurer site; the only
// caveat is that it's scraped, so brief upstream outages are possible.

import { supabase } from './supabase.js';
import { DatabaseError } from '../errors/index.js';

const SOURCE = {
  id: 'cook-county-treasurer',
  label: 'Cook County Treasurer',
  url: 'https://www.cookcountytreasurer.com/',
};

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
  if (!supabase) throw new DatabaseError({ meta: { reason: 'no-client' } });

  const clean = String(pin).replace(/\D/g, '');
  if (!/^\d{14}$/.test(clean)) {
    throw new DatabaseError({
      meta: { reason: 'invalid-pin', pin: String(pin) },
    });
  }

  const { data, error } = await supabase.functions.invoke('treasurer-lookup', {
    body: { pin: clean },
  });
  if (error) {
    throw new DatabaseError({ cause: error, meta: { pin: clean } });
  }
  if (!data || data.error) {
    throw new DatabaseError({
      meta: { pin: clean, detail: data?.error ?? 'no data' },
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
