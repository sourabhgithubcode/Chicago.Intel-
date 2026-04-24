/**
 * Chicago.Intel — Constants
 * Every magic number and string lives here.
 */

// ─── GEOGRAPHY ─────────────────────────────────────────
export const SAFETY_RADIUS_METERS = 402;          // 0.25 miles
export const AMENITY_RADIUS_METERS = 402;
export const BROADER_AMENITY_RADIUS_METERS = 805; // 0.5 miles

export const CHICAGO_BOUNDS = {
  north: 42.023, south: 41.644,
  east: -87.524, west: -87.940,
};

export const MAP_INITIAL_VIEW = {
  longitude: -87.6298, latitude: 41.8781,
  zoom: 11, pitch: 0, bearing: 0,
};

export const MAP_ZOOM_BREAKPOINTS = {
  cityToNeighborhood: 12,
  neighborhoodToStreet: 14,
  streetToBuilding: 16,
};

export const MAP_STYLE_URL = 'mapbox://styles/mapbox/light-v11';

// ─── DATA LIMITS ────────────────────────────────────────
export const MAX_SEARCH_RESULTS = 25;
export const MAX_AMENITIES_PER_CATEGORY = 10;
export const QUERY_TIMEOUT_MS = 10_000;

// ─── SALARY / RENT RANGES ──────────────────────────────
export const SALARY_RANGE = { min: 10_000, max: 1_000_000, step: 1_000, default: 65_000 };
export const RENT_RANGE = { min: 200, max: 20_000 };

// ─── UI ─────────────────────────────────────────────────
export const DEBOUNCE_MS = {
  search: 300,
  salarySlider: 150,
  mapZoom: 200,
};

// ─── COLOR SCALES ──────────────────────────────────────
export const SURPLUS_COLORS = {
  strong: '#b8ff6a',
  healthy: '#34d399',
  tight: '#fbbf24',
  stretch: '#fb923c',
  unaffordable: '#f87171',
};

export const SAFETY_COLORS = {
  high: '#34d399',
  moderate: '#fbbf24',
  low: '#fb923c',
  veryLow: '#f87171',
};

// ─── AMENITY CATEGORIES ────────────────────────────────
export const AMENITY_CATEGORIES = [
  { id: 'grocery', label: 'Grocery', icon: '🛒', googleType: 'grocery_or_supermarket', essential: true },
  { id: 'gym', label: 'Gym / Fitness', icon: '🏋️', googleType: 'gym', essential: false },
  { id: 'parking_paid', label: 'Parking (paid)', icon: '🅿️', googleType: 'parking', essential: false },
  { id: 'restaurant', label: 'Restaurants', icon: '🍽️', googleType: 'restaurant', essential: false },
  { id: 'coffee', label: 'Coffee', icon: '☕', googleType: 'cafe', essential: false },
  { id: 'laundry', label: 'Laundry', icon: '🧺', googleType: 'laundry', essential: true },
  { id: 'pet_care', label: 'Pet care', icon: '🐾', googleType: 'veterinary_care', essential: false },
  { id: 'medical', label: 'Medical', icon: '🏥', googleType: 'doctor', essential: true },
  { id: 'urgent_care', label: 'Urgent care', icon: '🚨', googleType: 'hospital', essential: true },
  { id: 'convenience', label: 'Convenience', icon: '🏪', googleType: 'convenience_store', essential: false },
  { id: 'liquor', label: 'Liquor', icon: '🍺', googleType: 'liquor_store', essential: false },
  { id: 'clothing', label: 'Clothing', icon: '👕', googleType: 'clothing_store', essential: false },
  { id: 'pharmacy', label: 'Pharmacy', icon: '💊', googleType: 'pharmacy', essential: true },
  { id: 'bank', label: 'Bank / ATM', icon: '🏦', googleType: 'atm', essential: false },
];

// ─── COPY ───────────────────────────────────────────────
export const COPY = {
  principle: 'Chicago.Intel shows you what public data says about any address in Chicago. We tell you how confident we are in each number and what it does not capture. You make the decision. We never tell you where to live.',
  emptyState: 'Enter an address to see building intelligence.',
  outOfBounds: 'This address is outside Chicago. We only cover Chicago addresses.',
  notFound: "We couldn't find that address. Double-check the spelling, or try a nearby intersection.",
  buildingNotFound: "We couldn't find building records for this address. May be in a new development or outside Cook County's data.",
};
