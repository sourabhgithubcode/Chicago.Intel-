/**
 * Chicago.Intel — Confidence Rating System
 *
 * Every data source has a documented confidence rating.
 * This is the single source of truth for all UI confidence labels.
 *
 * Ratings:
 * 9-10: Verifiable by user in under 5 minutes
 * 7-8:  Strong source with minor documented caveats
 * 6:    Directional signal — not a precise measurement
 * signal: Price tier or qualitative indicator only
 */

export const CONFIDENCE = {
  taxCalc: {
    score: 10,
    label: 'IRS 2024 law — exact',
    source: 'IRS Pub 15-T 2024 · IL DOR · SSA',
    caveat: null,
    verifyUrl: 'https://www.irs.gov/publications/p15t',
  },
  assessorOwner: {
    score: 9,
    label: 'Cook County Assessor',
    source: 'Cook County Assessor PIN database',
    caveat: 'LLC ownership may obscure individual landlord identity',
    verifyUrl: 'https://www.cookcountyassessoril.gov',
  },
  violations311: {
    score: 9,
    label: 'Chicago Data Portal',
    source: 'Chicago Data Portal · Chicago 311',
    caveat: 'Reflects reported complaints only',
    verifyUrl: 'https://data.cityofchicago.org',
  },
  ctaDistance: {
    score: 9,
    label: 'CTA GTFS official',
    source: 'CTA GTFS stops.txt — official feed',
    caveat: null,
    verifyUrl: 'https://www.transitchicago.com/developers/gtfs.aspx',
  },
  femaFlood: {
    score: 9,
    label: 'FEMA NFHL official',
    source: 'FEMA National Flood Hazard Layer API',
    caveat: 'Updated periodically — check msc.fema.gov for latest',
    verifyUrl: 'https://msc.fema.gov',
  },
  acsRentCCA: {
    score: 8,
    label: 'ACS 2019–23 · CCA level',
    source: 'ACS Table B25064 · 5-year estimates',
    caveat: 'Lags market by 2–3 years. Enter listed rent to override.',
    verifyUrl: 'https://data.census.gov',
  },
  safetyRadius: {
    score: 8,
    label: 'CPD · 0.25mi radius query',
    source: 'CPD IUCR incidents 2019–23 · coordinate radius',
    caveat: 'Reflects reported incidents only. Under-policed areas may show fewer reports — not fewer actual incidents.',
    verifyUrl: 'https://data.cityofchicago.org/Public-Safety/Crimes-2001-to-Present',
  },
  safetyCCA: {
    score: 7,
    label: 'CPD · CCA polygon',
    source: 'CPD IUCR incidents 2019–23 · aggregated to CCA boundary',
    caveat: 'CCA aggregation masks significant block-level variation. Reporting bias applies.',
    verifyUrl: 'https://data.cityofchicago.org',
  },
  googlePlacesTier: {
    score: 7,
    label: 'Google Places · signal only',
    source: 'Google Places API price_level field',
    caveat: 'Price tier is a relative signal ($/$$/$$$/$$$) — not a precise dollar amount. Individual shopping habits vary significantly.',
    verifyUrl: null,
    isSignal: true,
  },
  acsRentTract: {
    score: 6,
    label: 'ACS tract · higher MOE',
    source: 'ACS Table B25064 · tract-level · smaller sample',
    caveat: 'Tract-level data has higher margin of error than CCA. Use as directional guidance only.',
    verifyUrl: 'https://data.census.gov',
  },
  displacement: {
    score: 7,
    label: 'DePaul IHS + ACS',
    source: 'ACS time-series 2015–19 vs 2019–23 · DePaul IHS methodology',
    caveat: 'Displacement risk is a composite of multiple lagged indicators. Does not predict future displacement.',
    verifyUrl: 'https://www.housingstudies.org',
  },
  vibeScore: {
    score: 6,
    label: 'Yelp API · editorial',
    source: 'Yelp API + Park District + editorial calibration',
    caveat: 'Significant North Side bias in Yelp review density. South and West side neighborhoods are underrepresented.',
    verifyUrl: null,
    isSignal: true,
  },
  howLoudNoise: {
    score: 7,
    label: 'HowLoud API',
    source: 'HowLoud noise score API',
    caveat: 'Model-based estimate — not a physical measurement. Verify by visiting the block at different times.',
    verifyUrl: 'https://howloud.com',
  },
  compositeScore: {
    score: null,
    label: 'Editorial composite',
    source: 'Chicago.Intel weighted composite · see component breakdown',
    caveat: 'Weights reflect documented editorial judgment. View raw component scores to evaluate independently.',
    verifyUrl: null,
    isEditorial: true,
  },
};

/**
 * Returns confidence color for UI display
 * 9-10: green  7-8: blue  6: amber  signal: gray
 */
export function confidenceColor(score) {
  if (!score) return 'gray';
  if (score >= 9) return 'green';
  if (score >= 7) return 'blue';
  if (score >= 6) return 'amber';
  return 'gray';
}
