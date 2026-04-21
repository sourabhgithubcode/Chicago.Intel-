// API #17 / #18 — Sentry + GoatCounter wrappers.
// Sentry: captures ErrorBoundary crashes + API failures. Env: VITE_SENTRY_DSN
// GoatCounter: privacy-first pageview analytics. Env: VITE_GOATCOUNTER_URL
// Both are no-ops until the env vars are set — safe to import from anywhere.

const SENTRY_DSN = import.meta.env.VITE_SENTRY_DSN;
const GOATCOUNTER_URL = import.meta.env.VITE_GOATCOUNTER_URL;

export const sentryEnabled = Boolean(SENTRY_DSN);
export const analyticsEnabled = Boolean(GOATCOUNTER_URL);

let sentry = null;

export async function initMonitoring() {
  if (sentryEnabled && !sentry) {
    // TODO: install @sentry/react and wire init({ dsn: SENTRY_DSN }) here.
    // Left lazy so the bundle stays small until monitoring is actually on.
  }
  if (analyticsEnabled) {
    // TODO: inject GoatCounter <script data-goatcounter> tag in index.html
    // or call window.goatcounter.count() on route changes.
  }
}

export function captureException(err, meta = {}) {
  if (!sentryEnabled) {
    console.error('[captureException]', err, meta);
    return;
  }
  sentry?.captureException?.(err, { extra: meta });
}

export function trackEvent(name, meta = {}) {
  if (!analyticsEnabled) return;
  try {
    window.goatcounter?.count?.({ path: name, event: true, ...meta });
  } catch {
    // analytics must never crash the app
  }
}
