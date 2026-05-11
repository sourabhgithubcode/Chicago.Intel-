// Edge Function: treasurer-lookup
//
// Live per-PIN scrape of the Cook County Treasurer's "Property Tax Overview"
// page. Cook County publishes no API; this is the only path to current tax
// status. Confidence stays 9/10 because the source is the official site, but
// we cache aggressively (30d TTL) — the underlying bill changes at most twice
// a year.
//
// Request:  POST { pin: "<14 digits, no dashes>" }
// Response: { tax_year, total_billed, total_paid, amount_due, fetched_at, cached }
//
// Flow (matches the POC verified earlier):
//   1. GET  taxbillhistorysearch.aspx       → parse hidden ASP.NET form fields
//   2. POST setsearchparameters.aspx        → 5 PIN segments + form fields
//   3. Follow redirect to yourpropertytaxoverviewresults.aspx
//   4. Regex-extract billed / paid / due from the response text
//
// HTML parsing is intentionally regex-based — the surrounding markup is
// ASP.NET-generated and noisy, but the label strings ("Total Amount Billed",
// "Total Amount Paid", "Amount Due", "Tax Year YYYY") are stable.

import { createClient } from 'https://esm.sh/@supabase/supabase-js@2.39.0';

const TTL_MS = 30 * 24 * 60 * 60 * 1000; // 30d

const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

const BASE = 'https://www.cookcountytreasurer.com';
const SEARCH_URL = `${BASE}/taxbillhistorysearch.aspx`;
const SUBMIT_URL = `${BASE}/setsearchparameters.aspx`;

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...CORS_HEADERS, 'Content-Type': 'application/json' },
  });
}

function stripTags(html: string): string {
  return html
    .replace(/<script[\s\S]*?<\/script>/gi, ' ')
    .replace(/<style[\s\S]*?<\/style>/gi, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;/gi, ' ')
    .replace(/&amp;/g, '&')
    .replace(/\s+/g, ' ')
    .trim();
}

function extractHidden(html: string, name: string): string {
  // ASP.NET hidden inputs — id and name are the same, value follows in attrs.
  const re = new RegExp(
    `<input[^>]*name="${name}"[^>]*value="([^"]*)"`,
    'i'
  );
  const m = html.match(re);
  if (!m) {
    const re2 = new RegExp(
      `<input[^>]*value="([^"]*)"[^>]*name="${name}"`,
      'i'
    );
    const m2 = html.match(re2);
    if (!m2) throw new Error(`hidden field not found: ${name}`);
    return m2[1];
  }
  return m[1];
}

function parseMoney(s: string): number | null {
  const m = s.replace(/[, $]/g, '').match(/-?\d+(\.\d+)?/);
  return m ? Number(m[0]) : null;
}

function parseOverview(text: string) {
  // "Tax Year 2024 (billed in 2025) Total Amount Billed: $583,135.08"
  const yearMatch = text.match(/Tax Year\s+(\d{4})/i);
  const billed = text.match(/Total Amount Billed[:\s]*\$?([\d,]+\.\d{2})/i);
  const paid = text.match(/Total Amount Paid[:\s]*\$?([\d,]+\.\d{2})/i);
  const due = text.match(/(?:Total\s+)?Amount Due[:\s]*\$?([\d,]+\.\d{2})/i);

  return {
    tax_year: yearMatch ? Number(yearMatch[1]) : null,
    total_billed: billed ? parseMoney(billed[1]) : null,
    total_paid: paid ? parseMoney(paid[1]) : null,
    amount_due: due ? parseMoney(due[1]) : null,
  };
}

async function scrapeTreasurer(pin: string) {
  // Step 1 — GET search page, parse hidden form fields
  const getRes = await fetch(SEARCH_URL, {
    headers: {
      'User-Agent':
        'Mozilla/5.0 (compatible; chicago-intel/1.0; +https://chicago.intel)',
      Accept: 'text/html,application/xhtml+xml',
    },
  });
  if (!getRes.ok) {
    throw new Error(`treasurer GET ${getRes.status}`);
  }
  const getHtml = await getRes.text();

  const viewstate = extractHidden(getHtml, '__VIEWSTATE');
  const generator = extractHidden(getHtml, '__VIEWSTATEGENERATOR');
  const validation = extractHidden(getHtml, '__EVENTVALIDATION');

  // Step 2 — POST 5-segment PIN
  const seg = [
    pin.slice(0, 2),
    pin.slice(2, 4),
    pin.slice(4, 7),
    pin.slice(7, 10),
    pin.slice(10, 14),
  ];
  const prefix = 'ctl00$ContentPlaceHolder1$ASPxPanel1$SearchByPIN1';
  const form = new URLSearchParams();
  form.set('__VIEWSTATE', viewstate);
  form.set('__VIEWSTATEGENERATOR', generator);
  form.set('__EVENTVALIDATION', validation);
  form.set(`${prefix}$txtPIN1`, seg[0]);
  form.set(`${prefix}$txtPIN2`, seg[1]);
  form.set(`${prefix}$txtPIN3`, seg[2]);
  form.set(`${prefix}$txtPIN4`, seg[3]);
  form.set(`${prefix}$txtPIN5`, seg[4]);
  form.set(`${prefix}$cmdContinue`, 'Continue');

  const postRes = await fetch(SUBMIT_URL, {
    method: 'POST',
    redirect: 'follow',
    headers: {
      'User-Agent':
        'Mozilla/5.0 (compatible; chicago-intel/1.0; +https://chicago.intel)',
      'Content-Type': 'application/x-www-form-urlencoded',
      Referer: SEARCH_URL,
      Accept: 'text/html,application/xhtml+xml',
    },
    body: form.toString(),
  });
  if (!postRes.ok) {
    throw new Error(`treasurer POST ${postRes.status}`);
  }
  const html = await postRes.text();
  const text = stripTags(html);
  const parsed = parseOverview(text);

  if (
    parsed.tax_year == null &&
    parsed.total_billed == null &&
    parsed.amount_due == null
  ) {
    throw new Error('treasurer response missing all expected fields');
  }

  // Keep a short snippet of the parsed text for debugging the cache row.
  const snippet = text.slice(
    Math.max(0, text.search(/Tax Year/i) - 40),
    Math.max(0, text.search(/Tax Year/i) + 400)
  );

  return { ...parsed, raw_text: snippet };
}

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: CORS_HEADERS });
  if (req.method !== 'POST') return json({ error: 'method not allowed' }, 405);

  let body: { pin?: string };
  try {
    body = await req.json();
  } catch {
    return json({ error: 'invalid json' }, 400);
  }
  const pin = (body.pin ?? '').replace(/\D/g, '');
  if (!/^\d{14}$/.test(pin)) {
    return json({ error: 'pin must be 14 digits' }, 400);
  }

  const supabase = createClient(
    Deno.env.get('SUPABASE_URL')!,
    Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!,
  );

  // Cache hit (30d)
  const { data: cached } = await supabase
    .from('treasurer_cache')
    .select('pin, tax_year, total_billed, total_paid, amount_due, fetched_at')
    .eq('pin', pin)
    .maybeSingle();

  if (
    cached &&
    Date.now() - new Date(cached.fetched_at).getTime() < TTL_MS
  ) {
    return json({ ...cached, cached: true });
  }

  // Cache miss — scrape
  let scraped: Awaited<ReturnType<typeof scrapeTreasurer>>;
  try {
    scraped = await scrapeTreasurer(pin);
  } catch (err) {
    return json(
      {
        error: 'treasurer scrape failed',
        detail: err instanceof Error ? err.message : String(err),
      },
      500,
    );
  }

  const row = {
    pin,
    tax_year: scraped.tax_year,
    total_billed: scraped.total_billed,
    total_paid: scraped.total_paid,
    amount_due: scraped.amount_due,
    raw_text: scraped.raw_text,
    fetched_at: new Date().toISOString(),
  };

  const { error: upsertErr } = await supabase
    .from('treasurer_cache')
    .upsert(row, { onConflict: 'pin' });
  if (upsertErr) {
    return json(
      { error: 'cache upsert failed', detail: upsertErr.message },
      500,
    );
  }

  const { raw_text: _omit, ...resp } = row;
  return json({ ...resp, cached: false });
});
