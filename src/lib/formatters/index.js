// Display formatters.

// Census tracts have no human-readable names — only an 11-digit GEOID
// (SSCCCTTTTTT = state + county + 6-digit tract code). Render the GEOID as the
// standard short tract number the Census Bureau uses, e.g.
//   17031060100 → "Census Tract 601"   (tract code 0601.00)
//   17031010502 → "Census Tract 105.02"
export function tractLabel(geoid) {
  if (geoid == null) return 'Census Tract';
  const s = String(geoid);
  const n = Number(s.slice(-6)) / 100; // last 6 digits = tract code, last 2 are decimals
  if (!Number.isFinite(n)) return `Tract ${s}`;
  return `Census Tract ${Number.isInteger(n) ? n : n.toFixed(2)}`;
}
