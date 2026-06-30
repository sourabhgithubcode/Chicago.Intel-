// Best-effort brand logos for amenity map pins. Only well-known chains have a
// fetchable logo; everything else falls back to the category icon (handled by
// the marker's <img onError>). Logos via Clearbit (free, unofficial).

const DOMAINS = {
  starbucks: 'starbucks.com',
  dunkin: 'dunkindonuts.com',
  "dunkin'": 'dunkindonuts.com',
  mcdonalds: 'mcdonalds.com',
  "mcdonald's": 'mcdonalds.com',
  subway: 'subway.com',
  chipotle: 'chipotle.com',
  cvs: 'cvs.com',
  'cvs pharmacy': 'cvs.com',
  walgreens: 'walgreens.com',
  'jewel-osco': 'jewelosco.com',
  jewel: 'jewelosco.com',
  mariano: 'marianos.com',
  "mariano's": 'marianos.com',
  'whole foods': 'wholefoodsmarket.com',
  'whole foods market': 'wholefoodsmarket.com',
  target: 'target.com',
  walmart: 'walmart.com',
  aldi: 'aldi.us',
  'trader joe': 'traderjoes.com',
  "trader joe's": 'traderjoes.com',
  chase: 'chase.com',
  'bank of america': 'bankofamerica.com',
  'wells fargo': 'wellsfargo.com',
  'us bank': 'usbank.com',
  'fifth third': '53.com',
  'fifth third bank': '53.com',
  citibank: 'citi.com',
  'pnc bank': 'pnc.com',
  wintrust: 'wintrust.com',
  'bp shop': 'bp.com',
  bp: 'bp.com',
  shell: 'shell.com',
  mobil: 'mobil.com',
  '7-eleven': '7-eleven.com',
  fedex: 'fedex.com',
  ups: 'ups.com',
  usps: 'usps.com',
  'planet fitness': 'planetfitness.com',
  "la fitness": 'lafitness.com',
  xsport: 'xsportfitness.com',
};

/** Clearbit logo URL for a known chain name, or null (→ use the category icon). */
export function amenityLogoUrl(name) {
  if (!name) return null;
  const n = name.trim().toLowerCase();
  let domain = DOMAINS[n];
  if (!domain) {
    // loose contains-match for "Starbucks Reserve", "Chase Bank", etc.
    const hit = Object.keys(DOMAINS).find((k) => k.length > 3 && n.includes(k));
    domain = hit ? DOMAINS[hit] : null;
  }
  return domain ? `https://logo.clearbit.com/${domain}` : null;
}
