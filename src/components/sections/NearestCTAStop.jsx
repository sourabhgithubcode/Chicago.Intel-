// Nearest CTA stop for a building. First user-visible data point in the app —
// also the canonical example of the data-display contract:
//   value → source → confidence → caveats.

import { Train } from 'lucide-react';
import { useEffect, useState } from 'react';
import { getNearestCTAStop, getLastSyncedAt } from '../../lib/api/supabase.js';
import ConfidenceTag from './ConfidenceTag.jsx';

const formatDistance = (meters) => {
  if (meters == null) return '—';
  const miles = meters / 1609.34;
  if (miles < 0.1) return `${meters} m`;
  return `${miles.toFixed(2)} mi`;
};

function relTime(iso) {
  if (!iso) return 'never synced';
  const m = (Date.now() - new Date(iso).getTime()) / 60000;
  if (m < 60) return `synced ${Math.max(1, Math.round(m))}m ago`;
  if (m < 60 * 24) return `synced ${Math.round(m / 60)}h ago`;
  return `synced ${Math.round(m / 60 / 24)}d ago`;
}

export default function NearestCTAStop({ lat, lng }) {
  const [state, setState] = useState({ status: 'loading' });
  const [syncedAt, setSyncedAt] = useState(null);

  useEffect(() => {
    if (lat == null || lng == null) return undefined;
    let cancelled = false;
    Promise.all([
      getNearestCTAStop(lat, lng),
      getLastSyncedAt('cta').catch(() => null),
    ])
      .then(([data, synced]) => {
        if (cancelled) return;
        setSyncedAt(synced);
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
          <Train size={18} className="text-cyan" />
          Nearest CTA stop
        </h3>
        <div className="flex items-center gap-2">
          <span className="label-mono text-t3 text-xs">{relTime(syncedAt)}</span>
          <ConfidenceTag
            score={9}
            source={{
              label: 'CTA GTFS',
              url: 'https://www.transitchicago.com/developers/gtfs.aspx',
            }}
          />
        </div>
      </header>

      {state.status === 'loading' && (
        <p className="text-t2">Loading…</p>
      )}

      {state.status === 'error' && (
        <p className="text-rose">
          {state.err?.userMessage ?? 'Could not load CTA data.'}
        </p>
      )}

      {state.status === 'empty' && (
        <p className="text-t2">No CTA stop found near this address.</p>
      )}

      {state.status === 'ok' && (
        <>
          <div className="flex items-baseline gap-3">
            <span className="display text-3xl text-t0">
              {state.data.stop_name}
            </span>
            <span className="text-t2">
              {formatDistance(state.data.distance_m)} away
            </span>
          </div>

          {state.data.lines.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {state.data.lines.map((line) => (
                <span
                  key={line}
                  className="glass-3 label-mono px-2 py-0.5 text-cyan"
                >
                  {line}
                </span>
              ))}
            </div>
          ) : (
            <p className="text-t3 text-xs italic">
              Route lines not yet backfilled — see TODO in fetch_cta.py.
            </p>
          )}

          <details className="text-t2">
            <summary className="cursor-pointer text-t1 hover:text-t0">
              What this does not tell you
            </summary>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-xs">
              <li>Service frequency, headways, or hours of operation.</li>
              <li>
                Whether the route this stop serves goes where you actually
                need to go.
              </li>
              <li>Reliability or on-time performance.</li>
            </ul>
          </details>
        </>
      )}
    </section>
  );
}
