// Area-level scores at any zoom level — Community Area, Census Tract, or
// Citywide — each showing values recalculated for THAT level (tract scores are
// the tract's own; city is the aggregate across the 77 CCAs). Caller: App.jsx.

import { Activity, Bike, Bus, Clock, DollarSign, Footprints, Gauge, LayoutGrid, Shield, Sparkles, TrendingDown, Users, Wallet } from 'lucide-react';
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
    <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1 border-t border-slate-100 py-2 first:border-t-0 first:pt-0">
      <span className="label-mono text-t3 flex min-w-0 items-center gap-1.5 text-xs">
        {Icon && <Icon size={11} className="shrink-0" />}{labelNode}
      </span>
      <span className="flex min-w-0 items-center gap-2">
        <span className="text-t0 min-w-0 truncate">{value}</span>
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
      <header className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
        <h3 className="display flex min-w-0 items-center gap-2 text-xl text-t0">
          <LayoutGrid size={18} className="shrink-0 text-cyan" />
          <span className="min-w-0 break-words">{state.status === 'ok' ? d.name : scope.label}</span>
        </h3>
        <span className="label-mono text-t3 shrink-0 text-[10px] uppercase tracking-wide">{scope.label}</span>
      </header>

      {state.status === 'loading' && <p className="text-t2">Loading…</p>}
      {state.status === 'error' && <p className="text-rose">{state.err?.userMessage ?? 'Could not load scores.'}</p>}
      {state.status === 'empty' && <p className="text-t2">No data at this level.</p>}

      {state.status === 'ok' && (
        <>
          <div>
            <Row icon={Gauge} label="Overall score" value={score(d.composite_score)}
              tooltip="Weighted blend: affordability 40%, vulnerability 15%, safety 15%, walk 10%, displacement 10%, vibe 4%, bike 3%, run 3%. Normalized 1–10 across the 77 neighborhoods. A comparison — not a recommendation."
              confidence={6} source={{ label: 'Weighted blend' }} />
            <Row icon={Wallet} label="Affordability score" value={score(d.afford_score)}
              tooltip="Housing + transport cost ÷ $75,134 (Chicago median household income). Lower cost-share = higher score; HUD's 45% H+T benchmark ≈ 5/10. Because it divides by a fixed citywide income, very low-rent but distressed areas can still score as highly affordable. Our estimate — NOT HUD's published Location Affordability Index."
              confidence={6} source={{ label: 'ACS + our H+T model' }} />
            <Row icon={DollarSign} label="Median rent (ACS)"
              value={d.rent_median ? `$${d.rent_median.toLocaleString()}/mo` : null}
              tooltip={`Median gross rent, ACS 5-year estimate (2019–23) — ${scope.rentCaveat}.`}
              confidence={scope.conf} source={{ label: 'ACS 2019–23', url: 'https://data.census.gov/' }} />
            <Row icon={Bus} label="Transport cost (modeled)"
              value={d.transport_cost_mo ? `~$${d.transport_cost_mo.toLocaleString()}/mo` : null}
              tooltip="Modeled location transport cost: transit commuters × $75 CTA pass + autos/household × $12,297/yr (AAA 2024). An estimate of location-driven cost, not a bill."
              confidence={6} source={{ label: 'ACS + CTA/AAA' }} />
            <Row icon={Shield} label="Safety score" value={score(d.safety_score)}
              tooltip={`Per-capita CPD violent (×3) + property crime over 5 years, scaled to 10 at ${scope.label.toLowerCase()} level.`}
              confidence={scope.conf} source={{ label: 'CPD 2020–', url: 'https://data.cityofchicago.org/' }} />
            <Row icon={Activity} label="Walk score" value={score(d.walk_score)}
              tooltip="Transit + park access density. Signal only."
              confidence={6} source={{ label: 'CTA + Park District' }} />
            {scope.vibe && (
              <Row icon={Sparkles} label="Vibe score" value={score(d.vibe_score)}
                tooltip="Food/coffee/nightlife POI density (OpenStreetMap). Signal only — anchored to dense corridors, so most areas read low."
                confidence={6} source={{ label: 'OpenStreetMap' }} />
            )}
            <Row icon={TrendingDown} label="Displacement score" value={score(d.disp_score)}
              tooltip="Market-pressure index from UC Berkeley UDP typology; higher = greater risk."
              confidence={6} source={{ label: 'UDP / DePaul IHS' }} />
            {scope.vibe && (
              <Row icon={Users} label="Vulnerability score" value={score(d.vuln_score)}
                tooltip="Stability from ACS: below-poverty share + housing vacancy + income vs area median. Higher = more stable. Tenure shown as context, not scored."
                confidence={6} source={{ label: 'ACS 2019–23' }} />
            )}
            {scope.vibe && (
              <Row icon={Bike} label="Bikeability" value={score(d.bike_score)}
                tooltip="Cycleway (bike-lane) length density (OpenStreetMap). Signal only."
                confidence={6} source={{ label: 'OpenStreetMap' }} />
            )}
            {scope.vibe && (
              <Row icon={Footprints} label="Runnability" value={score(d.run_score)}
                tooltip="Park-area coverage + off-street path access (OpenStreetMap). Signal only."
                confidence={6} source={{ label: 'OpenStreetMap' }} />
            )}
            <Row icon={Clock} label="ACS data vintage" value={d.data_vintage}
              tooltip="Survey period for the ACS-derived figures (rent, affordability, vulnerability). Crime, displacement, and OSM signals each carry their own source and period in the rows above." />
          </div>

          <details className="text-t2">
            <summary className="cursor-pointer text-t1 hover:text-t0">What this does not tell you</summary>
            <p className="mt-2 pl-1 text-xs">
              {level === 'city'
                ? 'A citywide average hides huge block-to-block variation; use the neighborhood and tract views for local detail.'
                : 'Block-level variation within the area, and current market rents (ACS lags 2–3 years). Affordability divides housing + a modeled transport cost by Chicago’s median income ($75,134) — not your salary — so it reflects a typical earner, not you; it is our estimate, not HUD’s published Location Affordability Index.'}
            </p>
          </details>
        </>
      )}
    </section>
  );
}
