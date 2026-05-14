// Mapbox GL map — polygon updates as user navigates breadcrumb layers.
// city     → fly to Chicago overview
// cca      → CCA multipolygon from DB (migration 021), fit bounds
// tract    → tract multipolygon from DB (migration 021), fit bounds
// building → Mapbox building footprint via queryRenderedFeatures (OSM tiles),
//            falls back to 75m circle if tile doesn't have footprint data

import { useEffect, useState } from 'react';
import Map, { Layer, Source, useMap } from 'react-map-gl';
import { bbox, circle } from '@turf/turf';
import { getCcaGeojson, getTractGeojson } from '../lib/api/supabase.js';
import 'mapbox-gl/dist/mapbox-gl.css';

const TOKEN = import.meta.env.VITE_MAPBOX_TOKEN;
const CHICAGO = { longitude: -87.65, latitude: 41.85, zoom: 10 };

const FILL_LAYER = {
  id: 'poly-fill',
  type: 'fill',
  paint: { 'fill-color': 'rgba(37,99,235,0.10)', 'fill-outline-color': 'rgba(37,99,235,0)' },
};
const LINE_LAYER = {
  id: 'poly-line',
  type: 'line',
  paint: { 'line-color': 'rgba(37,99,235,0.80)', 'line-width': 2 },
};

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

    // ── Building — query Mapbox vector tile building footprint ────────────
    if (layer === 'building' && lat != null && lng != null) {
      map.flyTo({ center: [lng, lat], zoom: 17, duration: 800 });

      let stale = false;
      const onIdle = () => {
        if (stale) return;
        stale = true;
        map.off('idle', onIdle);

        const pt = map.project([lng, lat]);
        // Query Mapbox dark-v11 building footprint layer at the point
        const hits = map.queryRenderedFeatures(
          [[pt.x - 6, pt.y - 6], [pt.x + 6, pt.y + 6]],
          { layers: ['building'] }
        );

        if (hits.length > 0) {
          // Pick the polygon with the most vertices (the primary structure)
          const best = hits.reduce((a, b) => {
            const ca = a.geometry?.coordinates?.[0]?.length ?? 0;
            const cb = b.geometry?.coordinates?.[0]?.length ?? 0;
            return cb > ca ? b : a;
          });
          onGeoJson(best);
          const [w, s, e, n] = bbox(best);
          map.fitBounds([[w, s], [e, n]], { padding: 80, duration: 400, maxZoom: 18 });
        } else {
          // Fallback: 75m circle when building tile data isn't available
          const fallback = circle([lng, lat], 0.075, { steps: 48, units: 'kilometers' });
          onGeoJson(fallback);
          const [w, s, e, n] = bbox(fallback);
          map.fitBounds([[w, s], [e, n]], { padding: 80, duration: 400, maxZoom: 17 });
        }
      };

      map.on('idle', onIdle);
      return () => {
        stale = true;
        map.off('idle', onIdle);
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

export default function MapView({ layer, lat, lng, ccaId, tractGeoid }) {
  const [geoJson, setGeoJson] = useState(null);

  return (
    <Map
      mapboxAccessToken={TOKEN}
      initialViewState={CHICAGO}
      style={{ width: '100%', height: '100%' }}
      mapStyle="mapbox://styles/mapbox/light-v11"
    >
      <FlyController
        layer={layer}
        lat={lat}
        lng={lng}
        ccaId={ccaId}
        tractGeoid={tractGeoid}
        onGeoJson={setGeoJson}
      />

      {geoJson && (
        <Source id="poly" type="geojson" data={geoJson}>
          <Layer {...FILL_LAYER} />
          <Layer {...LINE_LAYER} />
        </Source>
      )}
    </Map>
  );
}
