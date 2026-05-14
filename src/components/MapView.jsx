// Mapbox GL map — polygon updates as user navigates breadcrumb layers.
// city     → fly to Chicago overview, no polygon
// cca      → CCA multipolygon, fit bounds
// tract    → tract multipolygon, fit bounds
// building → 75m radius circle polygon around the coordinate, zoom 16

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
  paint: { 'fill-color': 'rgba(56,189,248,0.15)', 'fill-outline-color': 'rgba(56,189,248,0)' },
};
const LINE_LAYER = {
  id: 'poly-line',
  type: 'line',
  paint: { 'line-color': 'rgba(56,189,248,0.85)', 'line-width': 2 },
};

function toFeature(geom) {
  if (!geom) return null;
  return { type: 'Feature', geometry: geom, properties: {} };
}

function FlyController({ layer, lat, lng, ccaId, tractGeoid, onGeoJson }) {
  const { current: map } = useMap();

  useEffect(() => {
    if (!map) return;

    if (layer === 'city') {
      map.flyTo({ center: [CHICAGO.longitude, CHICAGO.latitude], zoom: CHICAGO.zoom, duration: 800 });
      onGeoJson(null);
      return;
    }

    if (layer === 'building' && lat != null && lng != null) {
      const poly = circle([lng, lat], 0.075, { steps: 48, units: 'kilometers' });
      onGeoJson(poly);
      const [w, s, e, n] = bbox(poly);
      map.fitBounds([[w, s], [e, n]], { padding: 80, duration: 800, maxZoom: 17 });
      return;
    }

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
      mapStyle="mapbox://styles/mapbox/dark-v11"
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
