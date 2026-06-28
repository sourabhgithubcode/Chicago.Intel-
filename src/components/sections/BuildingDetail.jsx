// Building parcel facts (Cook County Assessor) at a coordinate, plus the
// 311-derived landlord record (violations + rodent, matched by address).
// Tax bill (treasurer) and flood_zone are still absent until those land.

import { Building2, Calendar, Camera, Crosshair, GraduationCap, Hash, Landmark, MapPin, ShieldAlert, User } from 'lucide-react';
import { useEffect, useState } from 'react';
import Map from 'react-map-gl';
import Tooltip from '../Tooltip.jsx';
import { getBuildingAt, getLastSyncedAt } from '../../lib/api/supabase.js';
import ConfidenceTag from './ConfidenceTag.jsx';

// Aerial photo of the building from Mapbox Static Images — uses the working
// Mapbox token (Google Street View needs the Street View Static API enabled,
// which isn't, so it returned no image).
const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN;

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
              tooltip="Taxpayer of record — often an LLC or trust, not the individual owner."
            />
            <Row
              icon={Calendar}
              label="year built"
              value={state.data.year_built ?? 'not recorded by Assessor'}
              tooltip="Construction year from the Assessor — often blank for condos and multi-unit parcels."
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
              tooltip="Weighted 311 building violations + rodent complaints at this address over 5 years; higher = cleaner record."
            />
            <Row
              icon={Crosshair}
              label="distance to point"
              value={`${state.data.distance_m} m`}
              tooltip="Meters from the parcel centroid to the exact coordinates you searched"
            />
          </div>

          {MAPBOX_TOKEN && (
            <div className="pt-1">
              <button
                onClick={() => setShowPhoto((v) => !v)}
                className="flex items-center gap-1.5 rounded-md bg-slate-100 px-3 py-1.5 text-xs font-medium text-t1 transition-colors hover:bg-slate-200"
              >
                <Camera size={12} />
                {showPhoto ? 'Hide building view' : 'View building (3D)'}
              </button>
              {showPhoto && (
                <figure className="mt-2">
                  <div className="h-72 w-full overflow-hidden rounded-lg border border-slate-200">
                    <Map
                      mapboxAccessToken={MAPBOX_TOKEN}
                      initialViewState={{ longitude: lng, latitude: lat, zoom: 17.5, pitch: 62, bearing: 30 }}
                      mapStyle="mapbox://styles/mapbox/standard"
                      style={{ width: '100%', height: '100%' }}
                    />
                  </div>
                  <figcaption className="text-t3 mt-1 text-[10px]">
                    3D buildings (Mapbox) · drag to pan · right-drag or ⌃-drag to circle · scroll to zoom
                  </figcaption>
                </figure>
              )}
            </div>
          )}

          <details className="text-t2">
            <summary className="cursor-pointer text-t1 hover:text-t0">
              What this does not tell you
            </summary>
            <p className="mt-2 pl-1 text-xs">
              About 30% of 311 complaints can't be address-matched, so "none on
              record" isn't a guarantee; owner is the taxpayer name, not the
              beneficial owner.
            </p>
          </details>
        </>
      )}
    </section>
  );
}
