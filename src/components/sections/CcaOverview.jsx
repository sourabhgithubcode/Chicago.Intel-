// CCA-level scores from the ccas table (ACS 2019-23 + CPD + Park District).
// Shown when user clicks a CCA name in the breadcrumb.

import { Activity, Clock, DollarSign, LayoutGrid, Shield, Sparkles, TrendingDown } from 'lucide-react';
import { useEffect, useState } from 'react';
import Tooltip from '../Tooltip.jsx';
import { getCcaById } from '../../lib/api/supabase.js';
import ConfidenceTag from './ConfidenceTag.jsx';

function Row({ icon: Icon, label, value, tooltip, confidence, source }) {
  if (value == null) return null;
  const labelNode = tooltip ? (
    <Tooltip content={tooltip}>
      <span className="cursor-help border-b border-dashed border-current">{label}</span>
    </Tooltip>
  ) : label;
  return (
    <div className="flex items-center justify-between gap-2 border-t border-slate-100 py-2 first:border-t-0 first:pt-0">
      <span className="label-mono text-t3 flex items-center gap-1.5 text-xs">
        {Icon && <Icon size={11} />}
        {labelNode}
      </span>
      <span className="flex items-center gap-2">
        <span className="text-t0">{value}</span>
        {confidence != null && <ConfidenceTag score={confidence} source={source} />}
      </span>
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
        <h3 className="display flex items-center gap-2 text-xl text-t0">
          <LayoutGrid size={18} className="text-cyan" />
          {state.status === 'ok' ? state.data.name : 'Neighborhood'}
        </h3>
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
              icon={DollarSign}
              label="Median rent (ACS)"
              value={state.data.rent_median ? `$${state.data.rent_median.toLocaleString()}/mo` : null}
              tooltip="Median gross rent across all renter households in this Community Area — ACS 5-year estimate (2019–23)"
              confidence={7}
              source={{ label: 'ACS 2019–23', url: 'https://data.census.gov/' }}
            />
            <Row
              icon={Shield}
              label="Safety score"
              value={score(state.data.safety_score)}
              tooltip="10 minus the per-capita rate of CPD violent (×3) + property crime over 5 years, scaled and clamped. Higher = safer. Per-capita basis can read harsh in low-residential / high-daytime areas."
              confidence={7}
              source={{ label: 'CPD 2020–', url: 'https://data.cityofchicago.org/' }}
            />
            <Row
              icon={Activity}
              label="Walk score"
              value={score(state.data.walk_score)}
              tooltip="Transit + park access density within the Community Area. Signal only — excludes amenity density and pedestrian infrastructure."
              confidence={6}
              source={{ label: 'CTA + Park District' }}
            />
            <Row
              icon={Sparkles}
              label="Vibe score"
              value={score(state.data.vibe_score)}
              tooltip="Composite of nearby dining, coffee, and entertainment density from Foursquare. Signal only — North Side bias."
              confidence={6}
              source={{ label: 'Foursquare' }}
            />
            <Row
              icon={TrendingDown}
              label="Displacement score"
              value={score(state.data.disp_score)}
              tooltip="Market-pressure index mapped from UC Berkeley UDP tract typology (2013–18). Higher = greater displacement risk."
              confidence={6}
              source={{ label: 'UDP / DePaul IHS' }}
            />
            <Row
              icon={Clock}
              label="Data vintage"
              value={state.data.data_vintage}
              tooltip="The survey period this data covers. ACS 5-year estimates lag current conditions by 2–3 years."
            />
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
