// Area-level scores at any zoom level — Community Area, Census Tract, or
// Citywide — each showing values recalculated for THAT level (tract scores are
// the tract's own; city is the aggregate across the 77 CCAs). Caller: App.jsx.

import { Activity, Clock, DollarSign, LayoutGrid, Shield, Sparkles, TrendingDown } from 'lucide-react';
import { useEffect, useState } from 'react';
import Tooltip from '../Tooltip.jsx';
import { getCcaById, getCityScores, getTractById } from '../../lib/api/supabase.js';
import ConfidenceTag from './ConfidenceTag.jsx';

const SCOPE = {
  cca:   { label: 'Community Area', rentCaveat: 'this neighborhood', conf: 7, vibe: true },
  tract: { label: 'Census Tract',   rentCaveat: 'this tract only',   conf: 6, vibe: false },
  city:  { label: 'Citywide',       rentCaveat: 'median of the 77 neighborhood medians', conf: 5, vibe: false },
};

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
        {Icon && <Icon size={11} />}{labelNode}
      </span>
      <span className="flex items-center gap-2">
        <span className="text-t0">{value}</span>
        {confidence != null && <ConfidenceTag score={confidence} source={source} />}
      </span>
    </div>
  );
}

const score = (n) => (n == null ? null : `${Number(n).toFixed(1)} / 10`);

export default function AreaScores({ level, id }) {
  const [state, setState] = useState({ status: 'loading' });
  const scope = SCOPE[level] ?? SCOPE.cca;

  useEffect(() => {
    if (level !== 'city' && id == null) return undefined;
    let cancelled = false;
    setState({ status: 'loading' });
    const p = level === 'tract' ? getTractById(id)
      : level === 'city' ? getCityScores()
      : getCcaById(id);
    p.then((data) => { if (!cancelled) setState(data ? { status: 'ok', data } : { status: 'empty' }); })
     .catch((err) => { if (!cancelled) setState({ status: 'error', err }); });
    return () => { cancelled = true; };
  }, [level, id]);

  const d = state.data;
  return (
    <section className="glass-2 space-y-3 p-5">
      <header className="flex items-center justify-between gap-3">
        <h3 className="display flex items-center gap-2 text-xl text-t0">
          <LayoutGrid size={18} className="text-cyan" />
          {state.status === 'ok' ? d.name : scope.label}
        </h3>
        <span className="label-mono text-t3 text-[10px] uppercase tracking-wide">{scope.label}</span>
      </header>

      {state.status === 'loading' && <p className="text-t2">Loading…</p>}
      {state.status === 'error' && <p className="text-rose">{state.err?.userMessage ?? 'Could not load scores.'}</p>}
      {state.status === 'empty' && <p className="text-t2">No data at this level.</p>}

      {state.status === 'ok' && (
        <>
          <div>
            <Row icon={DollarSign} label="Median rent (ACS)"
              value={d.rent_median ? `$${d.rent_median.toLocaleString()}/mo` : null}
              tooltip={`Median gross rent, ACS 5-year estimate (2019–23) — ${scope.rentCaveat}.`}
              confidence={scope.conf} source={{ label: 'ACS 2019–23', url: 'https://data.census.gov/' }} />
            <Row icon={Shield} label="Safety score" value={score(d.safety_score)}
              tooltip={`10 minus the per-capita rate of CPD violent (×3) + property crime over 5 years, scaled — ${scope.label.toLowerCase()} level. Per-capita can read harsh in low-residential areas.`}
              confidence={scope.conf} source={{ label: 'CPD 2020–', url: 'https://data.cityofchicago.org/' }} />
            <Row icon={Activity} label="Walk score" value={score(d.walk_score)}
              tooltip="Transit + park access density. Signal only — excludes amenity density and pedestrian infrastructure."
              confidence={6} source={{ label: 'CTA + Park District' }} />
            {scope.vibe && (
              <Row icon={Sparkles} label="Vibe score" value={score(d.vibe_score)}
                tooltip="Dining/coffee/entertainment density. Signal only — North Side bias."
                confidence={6} source={{ label: 'Foursquare' }} />
            )}
            <Row icon={TrendingDown} label="Displacement score" value={score(d.disp_score)}
              tooltip="Market-pressure index from UC Berkeley UDP typology (2013–18). Higher = greater displacement risk."
              confidence={6} source={{ label: 'UDP / DePaul IHS' }} />
            <Row icon={Clock} label="Data vintage" value={d.data_vintage}
              tooltip="The survey period this data covers. ACS 5-year estimates lag 2–3 years." />
          </div>

          <details className="text-t2">
            <summary className="cursor-pointer text-t1 hover:text-t0">What this does not tell you</summary>
            <p className="mt-2 pl-1 text-xs">
              {level === 'city'
                ? 'A citywide average hides huge block-to-block variation; use the neighborhood and tract views for local detail.'
                : 'Block-level variation within the area, and current market rents (ACS lags 2–3 years).'}
            </p>
          </details>
        </>
      )}
    </section>
  );
}
