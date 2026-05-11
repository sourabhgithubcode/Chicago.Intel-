// HowLoud sound score by lat/lng. PAID per call — 1yr cache (noise is static).
// Backed by /noise on the Render Flask service.
// Caller: future Noise section in BuildingDetail.
//
// Response components: airports/traffic/local numeric scores (0-100) plus
// descriptive text labels (Calm/Active/Busy). Overall score is composite.

const API = import.meta.env.VITE_TREASURER_API_URL;

const SOURCE = {
  id: 'howloud',
  label: 'HowLoud SoundScore',
  url: 'https://www.howloud.com/',
};

export async function getNoiseScore(lat, lng) {
  if (lat == null || lng == null) return null;
  if (!API) throw new Error('VITE_TREASURER_API_URL not set');

  const res = await fetch(`${API}/noise?lat=${lat}&lng=${lng}`);
  if (!res.ok) throw new Error(`Noise HTTP ${res.status}`);
  const data = await res.json();
  if (data.error) return null;

  const c = data.components || {};
  return {
    score: data.score,
    score_text: c.scoretext,
    traffic: c.traffic,
    traffic_text: c.traffictext,
    local: c.local,
    local_text: c.localtext,
    airports: c.airports,
    airports_text: c.airportstext,
    fetched_at: data.fetched_at,
    cached: !!data.cached,
    source: SOURCE,
    confidence: 7,
  };
}
