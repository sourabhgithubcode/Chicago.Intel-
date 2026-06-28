// Building-level amenity score — nearest grocery, pharmacy, laundry, transit,
// cafe, gym, restaurant, park, bank, ATM, post office, convenience, hotel
// within 0.25mi (Google Places + CTA). Score = distance-weighted, Essential
// 50% / Lifestyle 30% / Errands 20%. Caller: App.jsx (building layer).

import { Coffee, Dumbbell, Landmark, MapPin, ShoppingCart, Sparkles, Store, TramFront, TreePine, Truck, Utensils } from 'lucide-react';
import { useEffect, useState } from 'react';
import { getAmenityScore } from '../../lib/api/amenityScore.js';
import Tooltip from '../Tooltip.jsx';
import ConfidenceTag from './ConfidenceTag.jsx';

const ICONS = {
  grocery: ShoppingCart, pharmacy: Landmark, laundry: Truck, transit: TramFront,
  coffee: Coffee, gym: Dumbbell, restaurant: Utensils, park: TreePine,
  bank: Landmark, atm: Landmark, post_office: Truck, convenience: Store, hotel: Store,
};
const GROUPS = [
  { id: 'essential', title: 'Essentials' },
  { id: 'lifestyle', title: 'Lifestyle' },
  { id: 'errands', title: 'Errands' },
  { id: 'info', title: 'Also nearby' },
];
const walk = (m) => (m == null ? null : `~${Math.max(1, Math.round(m / 80))} min walk`);

function Item({ c }) {
  const Icon = ICONS[c.key] ?? MapPin;
  const list = c.nearest || [];
  return (
    <div className="flex flex-nowrap items-start justify-between gap-2 border-t border-slate-100 py-1.5 first:border-t-0">
      <span className="label-mono text-t3 flex shrink-0 items-center gap-1.5 pt-0.5 text-xs">
        <Icon size={11} /> {c.label}
      </span>
      <span className="text-t0 min-w-0 text-right text-sm">
        {list.length ? (
          <span className="flex flex-col items-end gap-0.5">
            {list.map((p, i) => (
              <span key={i} className="max-w-[15rem] truncate" title={p.name || undefined}>
                {p.name || 'found'}
                <span className="text-t3 ml-2 text-xs">· {p.dist} m · {walk(p.dist)}</span>
              </span>
            ))}
          </span>
        ) : (
          <span className="text-t3 text-xs italic">none nearby</span>
        )}
      </span>
    </div>
  );
}

export default function AmenityScore({ lat, lng }) {
  const [state, setState] = useState({ status: 'loading' });

  useEffect(() => {
    if (lat == null || lng == null) return undefined;
    let cancelled = false;
    setState({ status: 'loading' });
    getAmenityScore(lat, lng)
      .then((data) => { if (!cancelled) setState(data ? { status: 'ok', data } : { status: 'empty' }); })
      .catch((err) => { if (!cancelled) setState({ status: 'error', err }); });
    return () => { cancelled = true; };
  }, [lat, lng]);

  return (
    <section className="glass-2 space-y-3 p-5">
      <header className="flex items-center justify-between gap-3">
        <h3 className="display flex items-center gap-2 text-xl text-t0">
          <Sparkles size={18} className="text-cyan" />
          Amenities
        </h3>
        {state.status === 'ok' && (
          <div className="flex items-center gap-2">
            <Tooltip content="Walking distance to the nearest place in each category, weighted Essentials 50% / Lifestyle 30% / Errands 20%. Distance only.">
              <span className="text-t0 cursor-help border-b border-dashed border-current text-lg font-semibold">
                {state.data.score != null ? `${state.data.score} / 10` : '—'}
              </span>
            </Tooltip>
            <ConfidenceTag score={state.data.confidence} source={state.data.source} />
          </div>
        )}
      </header>

      {state.status === 'loading' && <p className="text-t2">Loading nearby places…</p>}
      {state.status === 'error' && (
        <p className="text-rose">{state.err?.userMessage ?? 'Could not load amenities.'}</p>
      )}
      {state.status === 'empty' && (
        <p className="text-t2">Nearby-places lookup is unavailable right now.</p>
      )}

      {state.status === 'ok' && (
        <>
          <div className="space-y-0">
            {GROUPS.map((g) => {
              const items = state.data.items.filter((c) => c.group === g.id);
              if (!items.length) return null;
              return (
                <div key={g.id} className="pt-1">
                  <p className="label-mono text-t3 pb-1 pt-2 text-[10px] uppercase tracking-wide">{g.title}</p>
                  {items.map((c) => <Item key={c.key} c={c} />)}
                </div>
              );
            })}
          </div>

          <details className="text-t2">
            <summary className="cursor-pointer text-t1 hover:text-t0">What this does not tell you</summary>
            <p className="mt-2 pl-1 text-xs">Distance only — not quality, price, hours, or whether the walk is actually pedestrian-friendly.</p>
          </details>
        </>
      )}
    </section>
  );
}
