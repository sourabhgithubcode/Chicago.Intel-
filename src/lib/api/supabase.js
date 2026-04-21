// API #1 — Supabase (Tier 1, required)
// Database + auto REST + RPC. Env: VITE_SUPABASE_URL, VITE_SUPABASE_ANON_KEY
// Failure mode: entire app down. Mitigation: retry + circuit breaker.

import { createClient } from '@supabase/supabase-js';
import { DatabaseError } from '../errors/index.js';
import { withRetry, CircuitBreaker } from '../retry/index.js';

const url = import.meta.env.VITE_SUPABASE_URL;
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

export const supabase = url && anonKey ? createClient(url, anonKey) : null;

const breaker = new CircuitBreaker({ name: 'supabase' });

export async function rpc(name, params = {}) {
  if (!supabase) throw new DatabaseError({ meta: { reason: 'no-client' } });
  return breaker.fire(() =>
    withRetry(async () => {
      const { data, error } = await supabase.rpc(name, params);
      if (error) throw new DatabaseError({ cause: error, meta: { name, params } });
      return data;
    })
  );
}
