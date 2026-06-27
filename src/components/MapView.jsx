// Mapbox GL map — polygon updates as user navigates breadcrumb layers.
// city     → fly to Chicago overview
// cca      → CCA multipolygon from DB (migration 021), fit bounds
// tract    → tract multipolygon from DB (migration 021), fit bounds
// building → Mapbox building footprint via queryRenderedFeatures (OSM tiles),
//            falls back to 75m circle if tile doesn't have footprint data

import { useEffect, useState } from 'react';
import Map, { Layer, Source, useMap } from 'react-map-gl';
import { bbox, circle } from '@turf/turf';
import { getBuildingFootprint, getCcaGeojson, getTractGeojson } from '../lib/api/supabase.js';
import 'mapbox-gl/dist/mapbox-gl.css';

const TOKEN = import.meta.env.VITE_MAPBOX_TOKEN;
const CHICAGO = { longitude: -87.65, latitude: 41.85, zoom: 10 };

// User-selectable base map styles (switcher control, top-right of the map).
const MAP_STYLES = [
  { id: 'light', label: 'Light', url: 'mapbox://styles/mapbox/light-v11' },
  { id: 'dark', label: 'Dark', url: 'mapbox://styles/mapbox/dark-v11' },
  { id: 'streets', label: 'Streets', url: 'mapbox://styles/mapbox/streets-v12' },
  { id: 'satellite', label: 'Satellite', url: 'mapbox://styles/mapbox/satellite-streets-v12' },
];

// Highlight layers. line/fill opacity is driven by `reveal` (0 → target) with a
// paint transition so each new boundary fades/draws in smoothly as the user
// zooms between levels instead of popping.
const TRANS = { duration: 600 };
function fillLayer(reveal) {
  return {
    id: 'poly-fill', type: 'fill',
    paint: { 'fill-color': 'rgba(37,99,235,0.12)', 'fill-opacity': reveal, 'fill-opacity-transition': TRANS },
  };
}
function lineLayer(reveal) {
  return {
    id: 'poly-line', type: 'line',
    paint: {
      'line-color': 'rgba(37,99,235,0.9)', 'line-width': 2.5,
      'line-opacity': reveal,
      'line-opacity-transition': TRANS, 'line-width-transition': TRANS,
    },
  };
}

function toFeature(geom) {
  if (!geom) return null;
  return { type: 'Feature', geometry: geom, properties: {} };
}

function FlyController({ layer, lat, lng, ccaId, tractGeoid, onGeoJson }) {
  const { current: map } = useMap();

  useEffect(() => {
    if (!map) return;

    // ── City ──────────────────────────────────────────────────────────────
    if (layer === 'city') {
      map.flyTo({ center: [CHICAGO.longitude, CHICAGO.latitude], zoom: CHICAGO.zoom, duration: 800 });
      onGeoJson(null);
      return;
    }

    // ── Building — exact footprint from our DB, then tile, then circle ────
    if (layer === 'building' && lat != null && lng != null) {
      map.flyTo({ center: [lng, lat], zoom: 18, duration: 800 });

      let stale = false;
      let detachIdle = null;

      // Mapbox vector-tile footprint / circle fallback (only when the DB has
      // no exact footprint near the point).
      const tileFallback = () => {
        const onIdle = () => {
          if (stale) return;
          stale = true;
          map.off('idle', onIdle);
          const pt = map.project([lng, lat]);
          const hits = map.queryRenderedFeatures(
            [[pt.x - 6, pt.y - 6], [pt.x + 6, pt.y + 6]],
            { layers: ['building'] }
          );
          if (hits.length > 0) {
            const best = hits.reduce((a, b) => {
              const ca = a.geometry?.coordinates?.[0]?.length ?? 0;
              const cb = b.geometry?.coordinates?.[0]?.length ?? 0;
              return cb > ca ? b : a;
            });
            onGeoJson(best);
            const [w, s, e, n] = bbox(best);
            map.fitBounds([[w, s], [e, n]], { padding: 80, duration: 400, maxZoom: 18 });
          } else {
            const fallback = circle([lng, lat], 0.075, { steps: 48, units: 'kilometers' });
            onGeoJson(fallback);
            const [w, s, e, n] = bbox(fallback);
            map.fitBounds([[w, s], [e, n]], { padding: 80, duration: 400, maxZoom: 17 });
          }
        };
        map.on('idle', onIdle);
        detachIdle = () => map.off('idle', onIdle);
      };

      // Exact footprint polygon from building_footprints (migration 029).
      getBuildingFootprint(lat, lng)
        .then((geom) => {
          if (stale) return;
          if (geom) {
            const feat = toFeature(geom);
            onGeoJson(feat);
            const [w, s, e, n] = bbox(feat);
            map.fitBounds([[w, s], [e, n]], { padding: 80, duration: 500, maxZoom: 19 });
          } else {
            tileFallback();
          }
        })
        .catch(() => { if (!stale) tileFallback(); });

      return () => {
        stale = true;
        if (detachIdle) detachIdle();
      };
    }

    // ── CCA — exact multipolygon from ccas table (migration 021) ──────────
    if (layer === 'cca') {
      if (ccaId != null) {
        getCcaGeojson(ccaId)
          .then((geom) => {
            if (!geom) {
              map.flyTo({ center: [lng, lat], zoom: 12, duration: 800 });
              onGeoJson(null);
              return;
            }
            const feat = toFeature(geom);
            onGeoJson(feat);
            const [w, s, e, n] = bbox(feat);
            map.fitBounds([[w, s], [e, n]], { padding: 40, duration: 800 });
          })
          .catch(() => {
            map.flyTo({ center: [lng, lat], zoom: 12, duration: 800 });
            onGeoJson(null);
          });
      } else {
        map.flyTo({ center: [lng, lat], zoom: 12, duration: 800 });
        onGeoJson(null);
      }
      return;
    }

    // ── Tract — exact multipolygon from tracts table (migration 021) ──────
    if (layer === 'tract') {
      if (tractGeoid != null) {
        getTractGeojson(tractGeoid)
          .then((geom) => {
            if (!geom) {
              map.flyTo({ center: [lng, lat], zoom: 14, duration: 800 });
              onGeoJson(null);
              return;
            }
            const feat = toFeature(geom);
            onGeoJson(feat);
            const [w, s, e, n] = bbox(feat);
            map.fitBounds([[w, s], [e, n]], { padding: 40, duration: 800 });
          })
          .catch(() => {
            map.flyTo({ center: [lng, lat], zoom: 14, duration: 800 });
            onGeoJson(null);
          });
      } else {
        map.flyTo({ center: [lng, lat], zoom: 14, duration: 800 });
        onGeoJson(null);
      }
    }
  }, [layer, lat, lng, ccaId, tractGeoid, map, onGeoJson]);

  return null;
}

// Tilts the camera for an angled 3D view (Google-Maps style). Building massing
// comes from the 3d-buildings fill-extrusion layer rendered below.
function PitchController({ threeD }) {
  const { current: map } = useMap();
  useEffect(() => {
    if (!map) return;
    map.easeTo({ pitch: threeD ? 60 : 0, bearing: threeD ? -20 : 0, duration: 700 });
  }, [threeD, map]);
  return null;
}

// 3D building massing from the vector style's building layer (gray extrusions —
// architectural massing, not photoreal). Present on light/dark/streets/sat-streets.
const BUILDINGS_3D = {
  id: '3d-buildings',
  source: 'composite',
  'source-layer': 'building',
  type: 'fill-extrusion',
  minzoom: 14,
  paint: {
    'fill-extrusion-color': '#9aa6b2',
    'fill-extrusion-height': ['coalesce', ['get', 'height'], 10],
    'fill-extrusion-base': ['coalesce', ['get', 'min_height'], 0],
    'fill-extrusion-opacity': 0.85,
  },
};

export default function MapView({ layer, lat, lng, ccaId, tractGeoid }) {
  const [geoJson, setGeoJson] = useState(null);
  const [styleId, setStyleId] = useState('light');
  const [reveal, setReveal] = useState(1);
  const [threeD, setThreeD] = useState(false);

  // On each new boundary, drop opacity to 0 then ease back to 1 — the paint
  // transition makes the border lines slide/adjust in smoothly.
  useEffect(() => {
    if (!geoJson) return undefined;
    setReveal(0);
    const id = setTimeout(() => setReveal(1), 40);
    return () => clearTimeout(id);
  }, [geoJson]);

  // A real Mapbox public token starts with "pk." — without one, mapbox-gl throws
  // and renders a blank panel. Degrade gracefully instead of spamming errors.
  if (!TOKEN || !TOKEN.startsWith('pk.')) {
    return (
      <div className="flex h-full w-full items-center justify-center bg-slate-100 p-8 text-center">
        <div className="max-w-xs">
          <p className="text-t1 text-sm font-semibold">Map unavailable</p>
          <p className="text-t2 mt-1 text-xs leading-relaxed">
            Set <code className="rounded bg-slate-200 px-1">VITE_MAPBOX_TOKEN</code> to a
            valid Mapbox public token to enable the map. All neighborhood data is in
            the panel on the left.
          </p>
        </div>
      </div>
    );
  }

  const mapStyle = (MAP_STYLES.find((s) => s.id === styleId) ?? MAP_STYLES[0]).url;

  return (
    <div className="relative h-full w-full">
      <Map
        mapboxAccessToken={TOKEN}
        initialViewState={CHICAGO}
        style={{ width: '100%', height: '100%' }}
        mapStyle={mapStyle}
      >
        <FlyController
          layer={layer}
          lat={lat}
          lng={lng}
          ccaId={ccaId}
          tractGeoid={tractGeoid}
          onGeoJson={setGeoJson}
        />
        <PitchController threeD={threeD} />

        {threeD && <Layer {...BUILDINGS_3D} />}

        {geoJson && (
          <Source id="poly" type="geojson" data={geoJson}>
            <Layer {...fillLayer(reveal)} />
            <Layer {...lineLayer(reveal)} />
          </Source>
        )}
      </Map>

      {/* Base-map style switcher + 3D toggle */}
      <div className="absolute right-3 top-3 z-10 flex gap-1 rounded-lg bg-white/90 p-1 shadow-md backdrop-blur">
        {MAP_STYLES.map((s) => (
          <button
            key={s.id}
            onClick={() => setStyleId(s.id)}
            className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
              styleId === s.id ? 'bg-cyan text-white' : 'text-t2 hover:bg-slate-100'
            }`}
          >
            {s.label}
          </button>
        ))}
        <span className="mx-0.5 w-px bg-slate-200" />
        <button
          onClick={() => setThreeD((v) => !v)}
          className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
            threeD ? 'bg-cyan text-white' : 'text-t2 hover:bg-slate-100'
          }`}
          title="Tilt for an angled 3D view with building massing"
        >
          3D
        </button>
      </div>
    </div>
  );
}
