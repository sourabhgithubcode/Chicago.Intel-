// Tax Bill (Cook County Treasurer) for a building PIN.
// Live scrape via the treasurer-lookup Edge Function with a 30d cache —
// see src/lib/api/treasurer.js. Renders only when a pin is present;
// BuildingDetail lifts its loaded pin up to App so this section can run.

import { useEffect, useState } from 'react';
import { getTreasurerData } from '../../lib/api/treasurer.js';
import ConfidenceTag from './ConfidenceTag.jsx';

const fmtMoney = (n) =>
  n == null
    ? null
    : `$${n.toLocaleString('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })}`;

function relTime(iso) {
  if (!iso) return 'never synced';
  const m = (Date.now() - new Date(iso).getTime()) / 60000;
  if (m < 60) return `synced ${Math.max(1, Math.round(m))}m ago`;
  if (m < 60 * 24) return `synced ${Math.round(m / 60)}h ago`;
  return `synced ${Math.round(m / 60 / 24)}d ago`;
}

function Row({ label, value }) {
  if (value == null || value === '') return null;
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-2 border-t border-white/5 py-2 first:border-t-0 first:pt-0">
      <span className="label-mono text-t3 text-xs">{label}</span>
      <span className="text-t0 text-right">{value}</span>
    </div>
  );
}

export default function TaxBill({ pin }) {
  const [state, setState] = useState({ status: 'idle' });

  useEffect(() => {
    if (!pin) {
      setState({ status: 'idle' });
      return undefined;
    }
    let cancelled = false;
    setState({ status: 'loading' });
    getTreasurerData(pin)
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
  }, [pin]);

  if (!pin) return null;

  const syncedAt = state.status === 'ok' ? state.data.fetched_at : null;

  return (
    <section className="glass-2 space-y-3 p-5">
      <header className="flex items-center justify-between gap-3">
        <h3 className="display text-xl text-t0">Tax Bill</h3>
        <div className="flex items-center gap-2">
          <span className="label-mono text-t3 text-xs">{relTime(syncedAt)}</span>
          <ConfidenceTag
            score={9}
            source={{
              label: 'Cook County Treasurer',
              url: 'https://www.cookcountytreasurer.com/',
            }}
          />
        </div>
      </header>

      {state.status === 'loading' && <p className="text-t2">Loading…</p>}

      {state.status === 'error' && (
        <p className="text-rose">
          {state.err?.userMessage ?? 'Could not load treasurer data.'}
        </p>
      )}

      {state.status === 'empty' && (
        <p className="text-t2">
          No Treasurer record returned for this PIN.
        </p>
      )}

      {state.status === 'ok' && (
        <>
          <div className="space-y-0">
            <Row label="tax year" value={state.data.tax_year} />
            <Row label="total billed" value={fmtMoney(state.data.total_billed)} />
            <Row label="total paid" value={fmtMoney(state.data.total_paid)} />
            <Row label="amount due" value={fmtMoney(state.data.amount_due)} />
          </div>

          <details className="text-t2">
            <summary className="cursor-pointer text-t1 hover:text-t0">
              What this does not tell you
            </summary>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-xs">
              <li>
                Whether the owner is on a payment plan — Treasurer shows the
                current balance, not the schedule behind it.
              </li>
              <li>
                Tax appeal or exemption status — appeals at the Board of
                Review or Assessor's office aren't reflected here.
              </li>
              <li>
                Refunds, prior-year delinquencies, or scavenger-sale history.
              </li>
              <li>
                This number is scraped from a public site that occasionally
                goes down — a stale cached read may be served for up to 30
                days.
              </li>
            </ul>
          </details>
        </>
      )}
    </section>
  );
}
