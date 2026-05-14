// CCA-level scores from the ccas table (ACS 2019-23 + CPD + Park District).
// Shown when user clicks a CCA name in the breadcrumb.

import { useEffect, useState } from 'react';
import { getCcaById } from '../../lib/api/supabase.js';
import ConfidenceTag from './ConfidenceTag.jsx';

function Row({ label, value }) {
  if (value == null) return null;
  return (
    <div className="flex items-baseline justify-between border-t border-white/5 py-2">
      <span className="label-mono text-t2 text-xs">{label}</span>
      <span className="text-t0">{value}</span>
    </div>
  );
}

function score(n) {
  if (n == null) return null;
  return `${Number(n).toFixed(1)} / 10`;
}

export default function CcaOverview({ ccaId }) {
  const [state, setState] = useState({ status: 'loading' });

  useEffect(() => {
    if (ccaId == null) return;
    let cancelled = false;
    getCcaById(ccaId)
      .then((data) => {
        if (cancelled) return;
        setState(data ? { status: 'ok', data } : { status: 'empty' });
      })
      .catch((err) => {
        if (cancelled) return;
        setState({ status: 'error', err });
      });
    return () => { cancelled = true; };
  }, [ccaId]);

  return (
    <section className="glass-2 space-y-3 p-5">
      <header className="flex items-center justify-between gap-3">
        <h3 className="display text-xl text-t0">
          {state.status === 'ok' ? state.data.name : 'Neighborhood'}
        </h3>
        <ConfidenceTag
          score={7}
          source={{ label: 'ACS 2019–23', url: 'https://data.census.gov/' }}
        />
      </header>

      {state.status === 'loading' && <p className="text-t2">Loading…</p>}
      {state.status === 'error' && (
        <p className="text-rose">{state.err?.userMessage ?? 'Could not load neighborhood data.'}</p>
      )}
      {state.status === 'empty' && (
        <p className="text-t2">No data for this neighborhood.</p>
      )}

      {state.status === 'ok' && (
        <>
          <div>
            <Row
              label="Median rent (ACS)"
              value={state.data.rent_median ? `$${state.data.rent_median.toLocaleString()}/mo` : null}
            />
            <Row label="Safety score"      value={score(state.data.safety_score)} />
            <Row label="Walk score"         value={score(state.data.walk_score)} />
            <Row label="Vibe score"         value={score(state.data.vibe_score)} />
            <Row label="Displacement score" value={score(state.data.disp_score)} />
            <Row label="Data vintage"       value={state.data.data_vintage} />
          </div>

          <details className="text-t2">
            <summary className="cursor-pointer text-t1 hover:text-t0">
              What this does not tell you
            </summary>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-xs">
              <li>Block- or street-level variation within the neighborhood.</li>
              <li>Current market rents — ACS 5-year estimates lag 2–3 years.</li>
              <li>How scores are trending — these are point-in-time values.</li>
            </ul>
          </details>
        </>
      )}
    </section>
  );
}
