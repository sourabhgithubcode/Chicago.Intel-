// Mapbox GL map — polygon updates as user navigates breadcrumb layers.
// city    → fly to Chicago overview, no polygon
// cca     → fetch + draw CCA multipolygon, fit bounds
// tract   → fetch + draw tract multipolygon, fit bounds
// building→ fly to coordinate, show pin marker

import { useEffect, useRef, useState } from 'react';
import Map, { Layer, Marker, Source, useMap } from 'react-map-gl';
import { getCcaGeojson, getTractGeojson } from '../lib/api/supabase.js';
import 'mapbox-gl/dist/mapbox-gl.css';

const TOKEN = import.meta.env.VITE_MAPBOX_TOKEN;
const CHICAGO = { longitude: -87.65, latitude: 41.85, zoom: 10 };

const FILL_LAYER = {
  id: 'poly-fill',
  type: 'fill',
  paint: { 'fill-color': 'rgba(56,189,248,0.12)', 'fill-outline-color': 'rgba(56,189,248,0)' },
};
const LINE_LAYER = {
  id: 'poly-line',
  type: 'line',
  paint: { 'line-color': 'rgba(56,189,248,0.75)', 'line-width': 1.5 },
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

    if (layer === 'building') {
      map.flyTo({ center: [lng, lat], zoom: 16, duration: 800 });
      onGeoJson(null);
      return;
    }

    if (layer === 'cca' && ccaId != null) {
      getCcaGeojson(ccaId).then((geom) => {
        if (!geom) return;
        onGeoJson(toFeature(geom));
        // fit bounds using turf bbox
        import('@turf/turf').then(({ bbox }) => {
          const [w, s, e, n] = bbox(toFeature(geom));
          map.fitBounds([[w, s], [e, n]], { padding: 40, duration: 800 });
        });
      }).catch(() => {});
      return;
    }

    if (layer === 'tract' && tractGeoid != null) {
      getTractGeojson(tractGeoid).then((geom) => {
        if (!geom) return;
        onGeoJson(toFeature(geom));
        import('@turf/turf').then(({ bbox }) => {
          const [w, s, e, n] = bbox(toFeature(geom));
          map.fitBounds([[w, s], [e, n]], { padding: 40, duration: 800 });
        });
      }).catch(() => {});
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

      {layer === 'building' && lat != null && lng != null && (
        <Marker longitude={lng} latitude={lat}>
          <div className="w-3 h-3 rounded-full bg-cyan shadow-glow-cyan" />
        </Marker>
      )}
    </Map>
  );
}
