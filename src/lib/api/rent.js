// RentCast rent estimate per PIN. PAID per call — 30d aggressive cache.
// Backed by /rent on the Render Flask service.
// Caller: future Rent Estimate section in BuildingDetail.

const API = import.meta.env.VITE_TREASURER_API_URL;

const SOURCE = {
  id: 'rentcast',
  label: 'RentCast AVM',
  url: 'https://www.rentcast.io/',
};

export async function getRentEstimate({ pin, bedrooms = 2, address }) {
  if (!pin || !address) return null;
  if (!API) throw new Error('VITE_TREASURER_API_URL not set');

  const params = new URLSearchParams({
    pin: String(pin).replace(/\D/g, ''),
    bedrooms: String(bedrooms),
    address,
  });
  const res = await fetch(`${API}/rent?${params}`);
  if (!res.ok) throw new Error(`Rent HTTP ${res.status}`);
  const data = await res.json();
  if (data.error) return null;
  return {
    rent: data.rent,
    rent_low: data.rent_low,
    rent_high: data.rent_high,
    bedrooms: data.bedrooms,
    fetched_at: data.fetched_at,
    cached: !!data.cached,
    source: SOURCE,
    confidence: 7,
  };
}
