// Tract-level displacement typology from UDP Chicago (UC Berkeley + SPARCC).
// 8 categories spanning "Stable / Advanced Exclusive" → "Ongoing Displacement".
// Vintage 2013–2018 ACS + 2012–2017 Zillow — confidence 6/10.

import { TrendingDown } from 'lucide-react';
import { useEffect, useState } from 'react';
import Tooltip from '../Tooltip.jsx';
import { getDisplacementAt } from '../../lib/api/supabase.js';
import ConfidenceTag from './ConfidenceTag.jsx';

export default function DisplacementRisk({ lat, lng }) {
  const [state, setState] = useState({ status: 'loading' });

  useEffect(() => {
    if (lat == null || lng == null) return undefined;
    let cancelled = false;
    getDisplacementAt(lat, lng)
      .then((data) => {
        if (cancelled) return;
        setState(data ? { status: 'ok', data } : { status: 'empty' });
      })
      .catch((err) => {
        if (cancelled) return;
        setState({ status: 'error', err });
      });
    return () => {
      cancelled = true;
    };
  }, [lat, lng]);

  return (
    <section className="glass-2 space-y-3 p-5">
      <header className="flex items-center justify-between gap-3">
        <h3 className="display flex items-center gap-2 text-xl text-t0">
          <TrendingDown size={18} className="text-amber" />
          <Tooltip content="UC Berkeley's UDP typology — classifies each census tract by market pressure and likelihood of resident displacement">
            <span className="cursor-help border-b border-dashed border-t0/30">Displacement risk</span>
          </Tooltip>
        </h3>
        <ConfidenceTag
          score={6}
          source={{
            label: 'UDP Chicago (UC Berkeley)',
            url: 'https://github.com/urban-displacement/displacement-typologies',
          }}
        />
      </header>

      {state.status === 'loading' && <p className="text-t2">Loading…</p>}

      {state.status === 'error' && (
        <p className="text-rose">
          {state.err?.userMessage ?? 'Could not load displacement data.'}
        </p>
      )}

      {state.status === 'empty' && (
        <p className="text-t2">
          No UDP typology for the tract at this point.
        </p>
      )}

      {state.status === 'ok' && (
        <>
          <div className="flex items-baseline gap-3">
            <Tooltip content="UDP typology label for this tract: ranges from 'Stable' → 'At Risk' → 'Ongoing Displacement' → 'Advanced Exclusive'">
              <span className="display cursor-help text-3xl text-t0 border-b border-dashed border-t0/30">
                {state.data.typology}
              </span>
            </Tooltip>
            <span className="text-t3 text-xs">
              <Tooltip content="Census Tract GEOID — a unique Census Bureau ID for this ~4,000-resident statistical area">
                <span className="cursor-help border-b border-dashed border-current">tract {state.data.geoid}</span>
              </Tooltip>
            </span>
          </div>

          <details className="text-t2">
            <summary className="cursor-pointer text-t1 hover:text-t0">
              What this does not tell you
            </summary>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-xs">
              <li>
                Current conditions — typology reflects 2013–2018 ACS + 2012–2017
                Zillow indices. UDP has not refreshed Chicago since 2018.
              </li>
              <li>
                Block- or building-level risk — this is a tract average
                (~4,000 residents), not your specific address.
              </li>
              <li>
                Causation — being labeled "at risk" describes market pressure,
                not whether any individual household will actually be displaced.
              </li>
            </ul>
          </details>
        </>
      )}
    </section>
  );
}
