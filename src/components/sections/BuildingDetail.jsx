// Building parcel facts (Cook County Assessor) at a coordinate.
// Renders only fields whose pipeline is wired today — tax bill (treasurer),
// 311-derived counters, landlord_score, and flood_zone are intentionally
// absent until their pipelines land.

import { Building2, Calendar, Crosshair, GraduationCap, Hash, Landmark, MapPin, User } from 'lucide-react';
import { useEffect, useState } from 'react';
import Tooltip from '../Tooltip.jsx';
import { getBuildingAt, getLastSyncedAt } from '../../lib/api/supabase.js';
import ConfidenceTag from './ConfidenceTag.jsx';

const fmtPrice = (n) =>
  n == null ? null : `$${n.toLocaleString('en-US')}`;

function relTime(iso) {
  if (!iso) return 'never synced';
  const m = (Date.now() - new Date(iso).getTime()) / 60000;
  if (m < 60) return `synced ${Math.max(1, Math.round(m))}m ago`;
  if (m < 60 * 24) return `synced ${Math.round(m / 60)}h ago`;
  return `synced ${Math.round(m / 60 / 24)}d ago`;
}

function Row({ icon: Icon, label, value, caveat, tooltip }) {
  if (value == null || value === '') return null;
  const labelNode = tooltip ? (
    <Tooltip content={tooltip}>
      <span className="cursor-help border-b border-dashed border-current">{label}</span>
    </Tooltip>
  ) : label;
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 py-2 first:border-t-0 first:pt-0">
      <span className="label-mono text-t3 flex items-center gap-1.5 text-xs">
        {Icon && <Icon size={11} />}
        {labelNode}
      </span>
      <span className="text-t0 text-right">
        {value}
        {caveat && (
          <span className="text-t3 ml-2 text-xs italic">· {caveat}</span>
        )}
      </span>
    </div>
  );
}

export default function BuildingDetail({ lat, lng, onLoaded }) {
  const [state, setState] = useState({ status: 'loading' });
  const [syncedAt, setSyncedAt] = useState(null);

  useEffect(() => {
    if (lat == null || lng == null) return undefined;
    let cancelled = false;
    setState({ status: 'loading' });
    Promise.all([
      getBuildingAt(lat, lng),
      getLastSyncedAt('assessor').catch(() => null),
    ])
      .then(([data, synced]) => {
        if (cancelled) return;
        setSyncedAt(synced);
        setState(data ? { status: 'ok', data } : { status: 'empty' });
        if (onLoaded) onLoaded(data ?? null);
      })
      .catch((err) => {
        if (cancelled) return;
        setState({ status: 'error', err });
        if (onLoaded) onLoaded(null);
      });
    return () => {
      cancelled = true;
    };
  }, [lat, lng, onLoaded]);

  return (
    <section className="glass-2 space-y-3 p-5">
      <header className="flex items-center justify-between gap-3">
        <h3 className="display flex items-center gap-2 text-xl text-t0">
          <Building2 size={18} className="text-cyan" />
          Building
        </h3>
        <div className="flex items-center gap-2">
          <span className="label-mono text-t3 text-xs">{relTime(syncedAt)}</span>
          <ConfidenceTag
            score={9}
            source={{
              label: 'Cook County Assessor',
              url: 'https://datacatalog.cookcountyil.gov/',
            }}
          />
        </div>
      </header>

      {state.status === 'loading' && <p className="text-t2">Loading…</p>}

      {state.status === 'error' && (
        <p className="text-rose">
          {state.err?.userMessage ?? 'Could not load building data.'}
        </p>
      )}

      {state.status === 'empty' && (
        <p className="text-t2">
          No Cook County parcel within 100 m of this point.
        </p>
      )}

      {state.status === 'ok' && (
        <>
          <div className="space-y-0">
            <Row icon={MapPin} label="address" value={state.data.address} />
            <Row
              icon={Hash}
              label="pin"
              value={state.data.pin}
              tooltip="Property Index Number — Cook County's unique 14-digit ID for every parcel"
            />
            <Row
              icon={User}
              label="owner"
              value={state.data.owner}
              caveat="taxpayer name; not beneficial owner"
              tooltip="Taxpayer of record from the Assessor. Often an LLC or trust, not the actual individual owner."
            />
            <Row icon={Calendar} label="year built" value={state.data.year_built} />
            <Row
              icon={Landmark}
              label="last sale"
              value={
                state.data.purchase_year
                  ? `${fmtPrice(state.data.purchase_price)} in ${
                      state.data.purchase_year
                    }`
                  : null
              }
            />
            <Row
              icon={GraduationCap}
              label="elementary school"
              value={state.data.school_elem}
              tooltip="Assigned CPS elementary school for this address per Cook County Assessor"
            />
            <Row
              icon={Crosshair}
              label="distance to point"
              value={`${state.data.distance_m} m`}
              tooltip="Meters from the parcel centroid to the exact coordinates you searched"
            />
          </div>

          <details className="text-t2">
            <summary className="cursor-pointer text-t1 hover:text-t0">
              What this does not tell you
            </summary>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-xs">
              <li>
                Current tax status or annual bill — Cook County Treasurer
                does not publish a public API; live lookup is queued.
              </li>
              <li>
                Building condition, violations, or 311 history — counters
                are populated by a separate reconcile pass not yet wired.
              </li>
              <li>
                Beneficial owner — owner field is the taxpayer's mailing
                name, which often differs from the actual owner via LLCs
                and trusts.
              </li>
            </ul>
          </details>
        </>
      )}
    </section>
  );
}
