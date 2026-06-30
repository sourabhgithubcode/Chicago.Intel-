// Mapbox GL map — polygon updates as user navigates breadcrumb layers.
// city     → fly to Chicago overview
// cca      → CCA multipolygon from DB (migration 021), fit bounds
// tract    → tract multipolygon from DB (migration 021), fit bounds
// building → Mapbox building footprint via queryRenderedFeatures (OSM tiles),
//            falls back to 75m circle if tile doesn't have footprint data

import { useEffect, useMemo, useState } from 'react';
import Map, { Layer, Marker, Source, useMap } from 'react-map-gl';
import { MapPin } from 'lucide-react';
import { AMENITY_ICONS } from './sections/AmenityScore.jsx';
import { amenityLogoUrl } from '../lib/amenityLogos.js';
import { bbox, circle } from '@turf/turf';
import { getBuildingFootprint, getBuildingsInTract, getCcaGeojson, getCcaScores, getTractScores, getTractGeojson } from '../lib/api/supabase.js';
import { allCcaFeatures } from '../lib/api/ccaStatic.js';
import { allTractFeatures, tractsInCca } from '../lib/api/tractStatic.js';
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
      // Thin but crisp borders — readable even with ~800 tracts on screen.
      // Solid navy, slightly thicker as you zoom in.
      'line-color': '#1e3a8a',
      'line-width': ['interpolate', ['linear'], ['zoom'], 10, 0.5, 13, 0.8, 16, 1.4],
      'line-opacity': reveal,
      'line-opacity-transition': TRANS, 'line-width-transition': TRANS,
    },
  };
}

function toFeature(geom) {
  if (!geom) return null;
  return { type: 'Feature', geometry: geom, properties: {} };
}

// "Color by" choropleth (city level). Each metric is a 0–10 score on the CCA.
const COLOR_METRICS = [
  { id: 'composite_score', label: 'Overall' },
  { id: 'afford_score', label: 'Affordability' },
  { id: 'safety_score', label: 'Safety' },
  { id: 'walk_score', label: 'Walk' },
  { id: 'disp_score', label: 'Displacement' },
  { id: 'vuln_score', label: 'Vulnerability' },
  { id: 'vibe_score', label: 'Vibe' },
  { id: 'bike_score', label: 'Bike' },
  { id: 'run_score', label: 'Run' },
];

// Tract level shades individual BUILDINGS by a building-specific metric (the 9
// areal metrics have no per-building value). Only well-populated columns.
const BUILDING_METRICS = [
  { id: 'violations_5yr', label: 'Violations' },
  { id: 'heat_complaints', label: 'Heat complaints' },
  { id: 'bug_reports', label: 'Bed-bug reports' },
  { id: 'year_built', label: 'Year built' },
];

// ColorBrewer "Blues" — a smooth 9-stop sequential ramp (light=low, dark=high).
const BLUE_RAMP = ['#f7fbff', '#deebf7', '#c6dbef', '#9ecae1', '#6baed6',
  '#4292c6', '#2171b5', '#08519c', '#08306b'];

// Stretch the ramp across the view's actual [lo, hi] so even a tight cluster of
// scores spans the full range of shades — slight differences stay visible at
// every level. Missing value (coalesced below the domain) → neutral gray.
function choroplethColor(metric, [lo, hi]) {
  const span = (hi - lo) || 1;
  const stops = BLUE_RAMP.flatMap((c, i) => [lo + (span * i) / (BLUE_RAMP.length - 1), c]);
  return ['interpolate', ['linear'], ['coalesce', ['get', metric], lo - span],
    lo - span, '#e5e7eb', ...stops];
}

function choroplethFillLayer(metric, domain) {
  return {
    id: 'poly-fill', type: 'fill',
    paint: { 'fill-color': choroplethColor(metric, domain), 'fill-opacity': 0.78, 'fill-opacity-transition': TRANS },
  };
}

// Tract-level building points, colored by the selected building metric (same
// stretched blue ramp), radius grows a touch as you zoom in.
// [min, max] of `metric` across the visible features → the stretch domain.
function _domain(features, metric) {
  const vals = (features || []).map((f) => f.properties?.[metric]).filter((v) => typeof v === 'number');
  if (!vals.length) return [0, 1];
  const lo = Math.min(...vals), hi = Math.max(...vals);
  return lo === hi ? [lo, lo + 1] : [lo, hi];
}

function buildingCircleLayer(metric, domain) {
  return {
    id: 'bldg-fill', type: 'circle',
    paint: {
      'circle-color': choroplethColor(metric, domain),
      'circle-radius': ['interpolate', ['linear'], ['zoom'], 12, 2.5, 16, 5, 18, 8],
      'circle-opacity': 0.85,
      'circle-stroke-width': 0.4,
      'circle-stroke-color': '#1e293b',
    },
  };
}

function FlyController({ layer, lat, lng, ccaId, tractGeoid, granularity, onGeoJson }) {
  const { current: map } = useMap();

  useEffect(() => {
    if (!map) return;

    // ── City — all 77 neighborhoods, or every tract (granularity='tracts') ──
    if (layer === 'city') {
      let stale = false;
      const source = granularity === 'tracts' ? allTractFeatures : allCcaFeatures;
      source()
        .then((fc) => {
          if (stale || !map) return;
          if (!fc?.features?.length) {
            map.flyTo({ center: [CHICAGO.longitude, CHICAGO.latitude], zoom: CHICAGO.zoom, duration: 800 });
            onGeoJson(null);
            return;
          }
          onGeoJson(fc);
          const [w, s, e, n] = bbox(fc);
          map.fitBounds([[w, s], [e, n]], { padding: 30, duration: 800 });
        })
        .catch(() => {
          if (stale || !map) return;
          map.flyTo({ center: [CHICAGO.longitude, CHICAGO.latitude], zoom: CHICAGO.zoom, duration: 800 });
          onGeoJson(null);
        });
      return () => { stale = true; };
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

    // ── CCA — granular: the CCA's tracts (choropleth); uniform: one polygon ──
    if (layer === 'cca') {
      if (ccaId == null) {
        map.flyTo({ center: [lng, lat], zoom: 12, duration: 800 });
        onGeoJson(null);
        return;
      }
      let stale = false;
      const fit = (data) => {
        const [w, s, e, n] = bbox(data);
        map.fitBounds([[w, s], [e, n]], { padding: 40, duration: 800 });
      };
      const single = () => getCcaGeojson(ccaId)
        .then((geom) => {
          if (stale) return;
          if (geom) { const f = toFeature(geom); onGeoJson(f); fit(f); }
          else { map.flyTo({ center: [lng, lat], zoom: 12, duration: 800 }); onGeoJson(null); }
        })
        .catch(() => { if (!stale) { map.flyTo({ center: [lng, lat], zoom: 12, duration: 800 }); onGeoJson(null); } });

      if (granularity === 'tracts') {
        tractsInCca(ccaId)
          .then((fc) => {
            if (stale) return;
            if (fc?.features?.length) { onGeoJson(fc); fit(fc); }
            else single();  // CCA with no mapped tracts → fall back to its outline
          })
          .catch(() => { if (!stale) single(); });
      } else {
        single();
      }
      return () => { stale = true; };
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
  }, [layer, lat, lng, ccaId, tractGeoid, granularity, map, onGeoJson]);

  return null;
}

// Building view flies tight to the footprint (z18), which leaves the amenity
// pins (up to 0.25mi out) off-screen. Once those pins load, pull the camera
// back to frame the building together with all its pins so they're visible by
// default. Keyed on amenityPoints only — does not re-run the footprint fetch.
function AmenityFitController({ layer, lat, lng, amenityPoints }) {
  const { current: map } = useMap();
  useEffect(() => {
    if (!map || layer !== 'building' || lat == null || lng == null) return;
    const pts = (amenityPoints || []).filter((p) => p.lat != null && p.lng != null);
    if (!pts.length) return;
    let minLng = lng, maxLng = lng, minLat = lat, maxLat = lat;
    for (const p of pts) {
      if (p.lng < minLng) minLng = p.lng;
      if (p.lng > maxLng) maxLng = p.lng;
      if (p.lat < minLat) minLat = p.lat;
      if (p.lat > maxLat) maxLat = p.lat;
    }
    map.fitBounds([[minLng, minLat], [maxLng, maxLat]], { padding: 70, duration: 700, maxZoom: 16.5 });
  }, [map, layer, lat, lng, amenityPoints]);
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

// Neighborhood name labels, shown only at the city level.
const LABEL_LAYER = {
  id: 'poly-label',
  type: 'symbol',
  layout: { 'text-field': ['get', 'name'], 'text-size': 11 },
  paint: { 'text-color': '#1e293b', 'text-halo-color': '#ffffff', 'text-halo-width': 1.3 },
};

// Building-view amenity pin — category icon (brand logo overlaid when known) +
// always-visible name label; highlights when its list row is hovered, & v.v.
function AmenityPin({ pt, hovered, onHover }) {
  const Icon = AMENITY_ICONS[pt.key] ?? MapPin;
  const logo = amenityLogoUrl(pt.name);
  return (
    <Marker longitude={pt.lng} latitude={pt.lat} anchor="bottom">
      <div
        onMouseEnter={() => onHover?.(pt.id)}
        onMouseLeave={() => onHover?.(null)}
        className="flex cursor-pointer flex-col items-center"
      >
        <div className={`flex max-w-[130px] items-center gap-1 rounded-full border bg-white/95 px-1.5 py-0.5 shadow-sm transition-transform ${
          hovered ? 'scale-110 border-cyan ring-2 ring-cyan/50' : 'border-slate-300'
        }`}>
          <span className="relative flex h-4 w-4 shrink-0 items-center justify-center">
            <Icon size={12} className="text-cyan" />
            {logo && <img src={logo} alt="" onError={(e) => { e.currentTarget.style.display = 'none'; }} className="absolute inset-0 h-4 w-4 rounded bg-white object-contain" />}
          </span>
          <span className="truncate text-[10px] font-medium text-slate-800">{pt.name || pt.label}</span>
        </div>
        <span className="-mt-px h-1.5 w-px bg-slate-500" />
      </div>
    </Marker>
  );
}

export default function MapView({ layer, lat, lng, ccaId, tractGeoid, onSelectArea, onSelectTract, onSelectBuilding, amenityPoints, hoveredAmenity, onHoverAmenity }) {
  const [geoJson, setGeoJson] = useState(null);
  const [styleId, setStyleId] = useState('light');
  const [reveal, setReveal] = useState(1);
  const [threeD, setThreeD] = useState(false);
  const [colorBy, setColorBy] = useState('composite_score');
  const [buildingColorBy, setBuildingColorBy] = useState('violations_5yr');
  const [ccaScores, setCcaScores] = useState(null);
  const [tractScores, setTractScores] = useState(null);
  const [buildings, setBuildings] = useState(null);
  // Map resolution — shade neighborhoods or their tracts. Applies at city +
  // neighborhood level; resets to the level's default on navigation.
  const [granularity, setGranularity] = useState('neighborhood'); // 'neighborhood' | 'tracts'

  // On each new boundary, drop opacity to 0 then ease back to 1 — the paint
  // transition makes the border lines slide/adjust in smoothly.
  useEffect(() => {
    if (!geoJson) return undefined;
    setReveal(0);
    const id = setTimeout(() => setReveal(1), 40);
    return () => clearTimeout(id);
  }, [geoJson]);

  // Each level starts at its natural resolution: city → neighborhoods, a
  // neighborhood → its tracts. The user can switch from there.
  useEffect(() => {
    setGranularity(layer === 'cca' ? 'tracts' : 'neighborhood');
  }, [layer]);

  // CCA + tract scores for the "color by" choropleth (loaded once each).
  // Plain objects, NOT `new Map` — `Map` is react-map-gl's component here.
  useEffect(() => {
    let stale = false;
    getCcaScores().then((rows) => {
      if (!stale) setCcaScores(Object.fromEntries(rows.map((r) => [r.id, r])));
    });
    getTractScores().then((rows) => {
      if (!stale) setTractScores(Object.fromEntries(rows.map((r) => [r.id, r])));
    });
    return () => { stale = true; };
  }, []);

  // Tract level: load the tract's buildings for the building choropleth.
  useEffect(() => {
    if (layer !== 'tract' || tractGeoid == null) { setBuildings(null); return undefined; }
    let stale = false;
    getBuildingsInTract(tractGeoid).then((fc) => { if (!stale) setBuildings(fc); });
    return () => { stale = true; };
  }, [layer, tractGeoid]);

  // Units shaded at the current view: tracts when granularity='tracts' (city =
  // all tracts, neighborhood = the CCA's tracts), else CCAs at city level.
  const showingTracts = granularity === 'tracts' && (layer === 'city' || layer === 'cca');
  const scoreById = showingTracts ? tractScores : layer === 'city' ? ccaScores : null;

  // Merge each shaded unit's scores into its feature properties so the
  // choropleth fill can read them via ['get', metric]. Only when geoJson is a
  // FeatureCollection (guards the single-Feature level-transition frame).
  const sourceData = useMemo(() => {
    if (!geoJson || !scoreById || !Array.isArray(geoJson.features)) return geoJson;
    return {
      ...geoJson,
      features: geoJson.features.map((f) => ({
        ...f,
        properties: { ...f.properties, ...(scoreById[f.properties?.id] ?? {}) },
      })),
    };
  }, [geoJson, scoreById]);

  const choroplethActive = !!scoreById && !!sourceData && Array.isArray(sourceData.features);
  const arealDomain = useMemo(() => _domain(sourceData?.features, colorBy), [sourceData, colorBy]);

  // Tract level: building points choropleth (own metric set + stretch domain).
  const buildingActive = layer === 'tract' && !!buildings && buildings.features.length > 0;
  const buildingDomain = useMemo(() => _domain(buildings?.features, buildingColorBy), [buildings, buildingColorBy]);

  // What a polygon/point click drills into, given what's shown.
  const clickUnit = showingTracts ? 'tract' : layer === 'city' ? 'cca' : null;

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
        interactiveLayerIds={choroplethActive ? ['poly-fill'] : buildingActive ? ['bldg-fill'] : []}
        cursor={choroplethActive || buildingActive ? 'pointer' : undefined}
        onClick={(e) => {
          const f = e.features?.[0];
          if (!f) return;
          if (f.layer?.id === 'poly-fill' && f.properties?.id != null) {
            if (clickUnit === 'cca' && onSelectArea) onSelectArea({ id: f.properties.id, name: f.properties.name });
            else if (clickUnit === 'tract' && onSelectTract) onSelectTract({ id: f.properties.id });
          } else if (f.layer?.id === 'bldg-fill' && onSelectBuilding) {
            const [blng, blat] = f.geometry.coordinates;
            onSelectBuilding({ lng: blng, lat: blat, pin: f.properties?.pin });
          }
        }}
      >
        <FlyController
          layer={layer}
          lat={lat}
          lng={lng}
          ccaId={ccaId}
          tractGeoid={tractGeoid}
          granularity={granularity}
          onGeoJson={setGeoJson}
        />
        <AmenityFitController layer={layer} lat={lat} lng={lng} amenityPoints={amenityPoints} />
        <PitchController threeD={threeD} />

        {threeD && <Layer {...BUILDINGS_3D} />}

        {sourceData && (
          <Source id="poly" type="geojson" data={sourceData}>
            <Layer {...(choroplethActive ? choroplethFillLayer(colorBy, arealDomain) : fillLayer(reveal))} />
            <Layer {...lineLayer(reveal)} />
            {layer === 'city' && granularity === 'neighborhood' && <Layer {...LABEL_LAYER} />}
          </Source>
        )}

        {buildingActive && (
          <Source id="bldgs" type="geojson" data={buildings}>
            <Layer {...buildingCircleLayer(buildingColorBy, buildingDomain)} />
          </Source>
        )}

        {layer === 'building' && (amenityPoints || []).map((pt) => (
          <AmenityPin key={pt.id} pt={pt} hovered={hoveredAmenity === pt.id} onHover={onHoverAmenity} />
        ))}
      </Map>

      {/* Top-left controls: granularity (city + neighborhood) + "Color by"
          (areal metrics on polygons, building metrics on the tract layer). */}
      {(choroplethActive || buildingActive || layer === 'city' || layer === 'cca') && (
        <div className="absolute left-3 top-3 z-10 max-w-[60%] rounded-lg bg-white/90 p-2 shadow-md backdrop-blur">
          {(layer === 'city' || layer === 'cca') && (
            <div className="mb-2 flex items-center gap-1 rounded-md bg-slate-100 p-0.5">
              {[['neighborhood', 'Neighborhood'], ['tracts', 'Tract']].map(([val, lbl]) => (
                <button
                  key={val}
                  onClick={() => setGranularity(val)}
                  className={`min-w-0 truncate rounded px-2 py-0.5 text-xs font-medium transition-colors ${
                    granularity === val ? 'bg-cyan text-white' : 'text-t2 hover:bg-white'
                  }`}
                >
                  {lbl}
                </button>
              ))}
            </div>
          )}
          {(choroplethActive || buildingActive) && (
            <>
              <label className="label-mono text-t3 mb-1 block text-[10px] uppercase tracking-wide">Color by</label>
              <select
                value={buildingActive ? buildingColorBy : colorBy}
                onChange={(e) => (buildingActive ? setBuildingColorBy : setColorBy)(e.target.value)}
                className="text-t1 max-w-full rounded-md border border-slate-200 bg-white px-2 py-1 text-xs"
              >
                {(buildingActive ? BUILDING_METRICS : COLOR_METRICS).map((m) => (
                  <option key={m.id} value={m.id}>{m.label}</option>
                ))}
              </select>
              <div className="mt-2 flex items-center gap-1">
                <span className="text-t3 text-[10px]">low</span>
                <span className="h-2 w-24 rounded" style={{ background: 'linear-gradient(90deg,#f7fbff,#6baed6,#08306b)' }} />
                <span className="text-t3 text-[10px]">high</span>
              </div>
            </>
          )}
        </div>
      )}

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
