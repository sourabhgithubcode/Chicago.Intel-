// AirNow current AQI by ZIP code. 1h cache.
// Backed by /aqi on the Render Flask service.
// Caller: future Air Quality section in BuildingDetail.

const API = import.meta.env.VITE_TREASURER_API_URL;

const SOURCE = {
  id: 'airnow',
  label: 'AirNow EPA',
  url: 'https://www.airnow.gov/',
};

export async function getAqi(zip) {
  if (!zip) return null;
  if (!API) throw new Error('VITE_TREASURER_API_URL not set');
  const clean = String(zip).replace(/\D/g, '');
  if (!/^\d{5}$/.test(clean)) throw new Error('zip must be 5 digits');

  const res = await fetch(`${API}/aqi?zip=${clean}`);
  if (!res.ok) throw new Error(`AQI HTTP ${res.status}`);
  const data = await res.json();
  if (data.error) return null;
  return {
    zip: data.zip,
    aqi: data.aqi,
    primary_pollutant: data.primary_pollutant,
    category: data.category,
    observed_at: data.source_observed_at,
    fetched_at: data.fetched_at,
    cached: !!data.cached,
    source: SOURCE,
    confidence: 9,
  };
}
