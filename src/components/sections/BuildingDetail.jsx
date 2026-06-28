// Building parcel facts (Cook County Assessor) at a coordinate, plus the
// 311-derived landlord record (violations + rodent, matched by address).
// Tax bill (treasurer) and flood_zone are still absent until those land.

import { Building2, Calendar, Camera, Crosshair, GraduationCap, Hash, Landmark, MapPin, ShieldAlert, User } from 'lucide-react';
import { useEffect, useState } from 'react';
import Tooltip from '../Tooltip.jsx';
import { getBuildingAt, getLastSyncedAt } from '../../lib/api/supabase.js';
import ConfidenceTag from './ConfidenceTag.jsx';

const GOOGLE_KEY = import.meta.env.VITE_GOOGLE_MAPS_KEY;
const streetViewUrl = (lat, lng) =>
  `https://maps.googleapis.com/maps/api/streetview?size=640x360&location=${lat},${lng}` +
  `&fov=80&pitch=8&source=outdoor&key=${GOOGLE_KEY}`;

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
    <div className="flex flex-nowrap items-center justify-between gap-2 border-t border-slate-100 py-2 first:border-t-0 first:pt-0">
      <span className="label-mono text-t3 flex shrink-0 items-center gap-1.5 text-xs">
        {Icon && <Icon size={11} />}
        {labelNode}
      </span>
      <span className="text-t0 min-w-0 truncate whitespace-nowrap text-right" title={typeof value === 'string' ? value : undefined}>
        {value}
        {caveat && (
          <span className="text-t3 ml-2 text-xs italic">· {caveat}</span>
        )}
      </span>
    </div>
  );
}

export default function BuildingDetail({ lat, lng, address, onLoaded }) {
  const [state, setState] = useState({ status: 'loading' });
  const [syncedAt, setSyncedAt] = useState(null);
  const [showPhoto, setShowPhoto] = useState(false);

  useEffect(() => {
    if (lat == null || lng == null) return undefined;
    let cancelled = false;
    setState({ status: 'loading' });
    Promise.all([
      getBuildingAt(lat, lng, address),
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
  }, [lat, lng, address, onLoaded]);

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
            <Row
              icon={Calendar}
              label="year built"
              value={state.data.year_built ?? 'not recorded by Assessor'}
              tooltip="Construction year from the Cook County Assessor characteristics file. Often blank for condos, vacant land, and some commercial / multi-unit parcels."
            />
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
              icon={ShieldAlert}
              label="landlord record (311)"
              value={
                state.data.landlord_score != null
                  ? `${Number(state.data.landlord_score).toFixed(1)} / 10`
                  : 'none matched to this address'
              }
              caveat={
                state.data.landlord_score != null
                  ? `${state.data.violations_5yr} bldg violations · ${state.data.bug_reports} rodent · 5yr`
                  : null
              }
              tooltip="Chicago 311 Building Violations (weighted) + rodent complaints filed at this address over 5 years, matched by address. Higher = cleaner record. Source: Chicago 311 (7/10)."
            />
            <Row
              icon={Crosshair}
              label="distance to point"
              value={`${state.data.distance_m} m`}
              tooltip="Meters from the parcel centroid to the exact coordinates you searched"
            />
          </div>

          {GOOGLE_KEY && (
            <div className="pt-1">
              <button
                onClick={() => setShowPhoto((v) => !v)}
                className="flex items-center gap-1.5 rounded-md bg-slate-100 px-3 py-1.5 text-xs font-medium text-t1 transition-colors hover:bg-slate-200"
              >
                <Camera size={12} />
                {showPhoto ? 'Hide building photo' : 'View building (Street View)'}
              </button>
              {showPhoto && (
                <figure className="mt-2">
                  <img
                    src={streetViewUrl(lat, lng)}
                    alt="Street View of the building"
                    className="w-full rounded-lg border border-slate-200"
                    loading="lazy"
                    onError={(e) => { e.currentTarget.parentElement.style.display = 'none'; }}
                  />
                  <figcaption className="text-t3 mt-1 text-[10px]">
                    Google Street View · nearest road-level capture · may show an adjacent frontage
                  </figcaption>
                </figure>
              )}
            </div>
          )}

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
                Violations are matched to this address from Chicago 311; about
                30% of complaints (intersection/format mismatches) can't be
                matched, so "no violations on record" is not a guarantee. A low
                score reflects complaint volume, which rises with building size.
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
