/**
 * Chicago.Intel — Config
 * Single source of truth for env vars. Fails fast on startup.
 */

const required = {
  supabaseUrl: import.meta.env.VITE_SUPABASE_URL,
  supabaseAnonKey: import.meta.env.VITE_SUPABASE_ANON_KEY,
  googleMapsKey: import.meta.env.VITE_GOOGLE_MAPS_KEY,
  mapboxToken: import.meta.env.VITE_MAPBOX_TOKEN,
};

const optional = {
  googlePlacesKey: import.meta.env.VITE_GOOGLE_PLACES_KEY ?? import.meta.env.VITE_GOOGLE_MAPS_KEY,
  rentcastKey: import.meta.env.VITE_RENTCAST_KEY ?? null,
  howLoudKey: import.meta.env.VITE_HOWLOUD_KEY ?? null,
  airnowKey: import.meta.env.VITE_AIRNOW_KEY ?? null,
  yelpKey: import.meta.env.VITE_YELP_KEY ?? null,
  sentryDsn: import.meta.env.VITE_SENTRY_DSN ?? null,
  goatCounterUrl: import.meta.env.VITE_GOATCOUNTER_URL ?? null,
};

const missing = Object.entries(required)
  .filter(([, value]) => !value)
  .map(([key]) => key);

if (missing.length > 0) {
  const msg = `Missing required env vars: ${missing.join(', ')}. Check .env.local.`;
  if (import.meta.env.DEV) throw new Error(msg);
  else console.error(msg);
}

export default {
  ...required,
  ...optional,
  environment: import.meta.env.MODE,
  isDev: import.meta.env.DEV,
  isProd: import.meta.env.PROD,
  features: {
    realVariableModel: import.meta.env.VITE_FEATURE_REAL_MODEL !== 'false',
    amenityLayer: import.meta.env.VITE_FEATURE_AMENITIES !== 'false',
    compositeScore: import.meta.env.VITE_FEATURE_COMPOSITE !== 'false',
    compareBuildings: import.meta.env.VITE_FEATURE_COMPARE !== 'false',
    shareReport: import.meta.env.VITE_FEATURE_SHARE !== 'false',
  },
};
