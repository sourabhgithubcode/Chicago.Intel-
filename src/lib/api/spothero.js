// API #14 — SpotHero (Tier 4, partnership required, V3+)
// Real monthly parking rates. Not publicly available.
// Fallback: Chicago Data Portal parking-meters dataset pulled in pipeline.

export const enabled = false;

export async function monthlyParking() {
  throw new Error(
    'SpotHero requires a partnership — use the Chicago Data Portal parking-meters dataset until approved.'
  );
}
