// Building-level amenity score from nearby places (OpenStreetMap via the
// /amenities_all proxy — one batched call) + transit from our own CTA data.
// Each category is scored by distance to its nearest instance, then weighted:
// Essential 50% / Lifestyle 30% / Errands 20% (per CLAUDE.md amenity weights).
// Hotels are shown but not scored. Caller: AmenityScore.jsx.

import { getAmenitiesAll } from './amenities.js';
import { getNearestCTAStop } from './supabase.js';

const CATS = [
  { key: 'grocery',     label: 'Grocery',          group: 'essential' },
  { key: 'pharmacy',    label: 'Pharmacy',         group: 'essential' },
  { key: 'laundry',     label: 'Laundry',          group: 'essential' },
  { key: 'coffee',      label: 'Cafe',             group: 'lifestyle' },
  { key: 'gym',         label: 'Gym',              group: 'lifestyle' },
  { key: 'restaurant',  label: 'Restaurant',       group: 'lifestyle' },
  { key: 'park',        label: 'Park',             group: 'lifestyle' },
  { key: 'bank',        label: 'Bank',             group: 'errands' },
  { key: 'atm',         label: 'ATM',              group: 'errands' },
  { key: 'post_office', label: 'Post office (USPS)', group: 'errands' },
  { key: 'convenience', label: 'Convenience store', group: 'errands' },
  { key: 'hotel',       label: 'Hotel',            group: 'info' }, // shown, not scored
];

const GROUP_WEIGHT = { essential: 0.5, lifestyle: 0.3, errands: 0.2 };

// Distance (m) → 0..10 sub-score. <=150m = 10 (on your block), >=800m = 0
// (>10 min walk), linear between. Proximity is a measurement, not a price tier.
function distScore(m) {
  if (m == null) return 0;
  if (m <= 150) return 10;
  if (m >= 800) return 0;
  return +(10 * (800 - m) / (800 - 150)).toFixed(1);
}

export async function getAmenityScore(lat, lng) {
  if (lat == null || lng == null) return null;

  let cats = {};
  try { cats = (await getAmenitiesAll(lat, lng)) || {}; } catch { cats = {}; }
  const results = CATS.map((c) => {
    const nearest = (cats[c.key] ?? [])
      .filter((p) => p.distance_m != null)
      .sort((x, y) => x.distance_m - y.distance_m)
      .slice(0, 2)
      .map((p) => ({ name: p.name ?? null, dist: p.distance_m }));
    return { ...c, nearest, dist: nearest[0]?.dist ?? null };
  });

  let cta = null;
  try { cta = await getNearestCTAStop(lat, lng); } catch { /* transit optional */ }
  const transit = {
    key: 'transit', label: 'Transit (CTA)', group: 'essential',
    nearest: cta?.stop_name ? [{ name: cta.stop_name, dist: cta.distance_m }] : [],
    dist: cta?.distance_m ?? null,
  };
  const items = [...results, transit];

  // If every Google-backed category is empty, Places is down (key/403) — don't
  // show a misleading transit-only score; report unavailable instead.
  const googleScored = results.filter((c) => c.group !== 'info');
  if (googleScored.every((c) => c.dist == null)) return null;

  // composite: average sub-score within each weight group, then weight groups
  const byGroup = {};
  for (const c of items) {
    if (c.group === 'info') continue;
    (byGroup[c.group] ??= []).push(distScore(c.dist));
  }
  let composite = 0, wsum = 0;
  for (const g of Object.keys(GROUP_WEIGHT)) {
    const arr = byGroup[g] || [];
    if (!arr.length) continue;
    composite += (arr.reduce((a, b) => a + b, 0) / arr.length) * GROUP_WEIGHT[g];
    wsum += GROUP_WEIGHT[g];
  }

  return {
    score: wsum ? +(composite / wsum).toFixed(1) : null,
    items,
    weights: GROUP_WEIGHT,
    source: {
      id: 'google-places',
      label: 'Google Places + CTA',
      url: 'https://developers.google.com/maps/documentation/places/web-service',
    },
    confidence: 7,
  };
}
