// API #3 — Mapbox GL JS (Tier 1, required)
// Not a REST client — consumed directly by react-map-gl. This module just
// centralizes the access-token lookup so every map component reads from
// one place. Env: VITE_MAPBOX_TOKEN (URL-restricted).

export const mapboxToken = import.meta.env.VITE_MAPBOX_TOKEN;

export const MAPBOX_STYLE = 'mapbox://styles/mapbox/dark-v11';
