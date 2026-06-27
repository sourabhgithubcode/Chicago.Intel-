import { useCallback, useEffect, useRef, useState } from 'react';
import Breadcrumb from './components/Breadcrumb.jsx';
import MapView from './components/MapView.jsx';
import AmenityScore from './components/sections/AmenityScore.jsx';
import BuildingDetail from './components/sections/BuildingDetail.jsx';
import CcaOverview from './components/sections/CcaOverview.jsx';
import DisplacementRisk from './components/sections/DisplacementRisk.jsx';
import NearestCTAStop from './components/sections/NearestCTAStop.jsx';
import SearchBar from './components/sections/SearchBar.jsx';
import TaxBill from './components/sections/TaxBill.jsx';
import { getCcaAt, getTractAt } from './lib/api/supabase.js';
import { reverseGeocode } from './lib/api/geocode.js';

// Chicago bounding box — geolocation outside it falls back to the type-prompt.
const CHI = { w: -87.940, e: -87.524, s: 41.644, n: 42.023 };

export default function App() {
  const [target, setTarget] = useState(null);
  const [pin, setPin] = useState(null);
  const [layer, setLayer] = useState('building');
  const [context, setContext] = useState({ cca: null, tract: null });
  const [geoStatus, setGeoStatus] = useState('locating'); // locating | denied
  const [splitPct, setSplitPct] = useState(50);
  const dragging = useRef(false);
  const containerRef = useRef(null);

  useEffect(() => {
    const onMove = (e) => {
      if (!dragging.current || !containerRef.current) return;
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
      const rect = containerRef.current.getBoundingClientRect();
      const pct = Math.min(Math.max(((e.clientX - rect.left) / rect.width) * 100, 25), 75);
      setSplitPct(pct);
    };
    const onUp = () => {
      dragging.current = false;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, []);

  const handleResult = useCallback(({ lat, lng, address }) => {
    const zip = /\b(\d{5})\b/.exec(address)?.[1] ?? null;
    setTarget({ lat, lng, address, zip });
    setPin(null);
    setLayer('building');
    // Resolve CCA + tract for breadcrumb labels and map polygons
    Promise.all([
      getCcaAt(lat, lng).catch(() => null),
      getTractAt(lat, lng).catch(() => null),
    ]).then(([cca, tract]) => setContext({ cca, tract }));
  }, []);

  const handleBuildingLoaded = useCallback((b) => {
    setPin(b?.pin ?? null);
  }, []);

  // On load, offer to use the browser's location. In-Chicago → show that
  // address by default; denied / off-Chicago / unsupported → type-address prompt.
  useEffect(() => {
    if (!('geolocation' in navigator)) { setGeoStatus('denied'); return; }
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        const { latitude: lat, longitude: lng } = pos.coords;
        if (lat < CHI.s || lat > CHI.n || lng < CHI.w || lng > CHI.e) {
          setGeoStatus('denied');
          return;
        }
        const address = (await reverseGeocode(lat, lng)) || 'Your location';
        handleResult({ lat, lng, address });
      },
      () => setGeoStatus('denied'),
      { timeout: 8000, maximumAge: 600000 },
    );
  }, [handleResult]);

  return (
    <div ref={containerRef} className="flex h-screen overflow-hidden bg-bg">
      {/* ── Left: scrollable data panel ── */}
      <div style={{ width: `calc(${splitPct}% - 4px)` }} className="flex-shrink-0 overflow-y-auto">
        <div className="flex flex-col gap-4 p-6">
          <header className="glass-1 space-y-2 p-6 text-center">
            <div className="label-mono text-t2 text-xs">chicago · intel · v2</div>
            <h1 className="display text-4xl text-t0">Chicago.Intel</h1>
            <p className="text-t2 text-sm leading-relaxed">
              Neighborhood intelligence for Chicago renters.
            </p>
            {/* Permanent UI copy (CLAUDE.md — do not change) */}
            <p className="text-t3 mx-auto max-w-md border-t border-slate-100 pt-3 text-xs leading-relaxed">
              Chicago.Intel shows you what public data says about any address in
              Chicago. We tell you how confident we are in each number and what it
              does not capture. You make the decision. We never tell you where to live.
            </p>
          </header>

          <SearchBar onResult={handleResult} />

          {!target ? (
            <p className="text-t2 text-sm text-center py-8">
              {geoStatus === 'locating'
                ? 'Locating you…'
                : 'Type a Chicago address above to begin.'}
            </p>
          ) : (
            <>
              <Breadcrumb
                layer={layer}
                ccaName={context.cca?.name}
                tractId={context.tract?.id}
                address={target.address}
                onLayerChange={setLayer}
              />

              {/* ── Layer-specific data sections ── */}
              {layer === 'cca' && <CcaOverview ccaId={context.cca?.id} />}

              {layer === 'tract' && (
                <>
                  <NearestCTAStop lat={target.lat} lng={target.lng} />
                  <DisplacementRisk lat={target.lat} lng={target.lng} />
                </>
              )}

              {layer === 'building' && (
                <>
                  <BuildingDetail
                    lat={target.lat}
                    lng={target.lng}
                    address={target.address}
                    onLoaded={handleBuildingLoaded}
                  />
                  <TaxBill pin={pin} />
                  <AmenityScore lat={target.lat} lng={target.lng} />
                  <NearestCTAStop lat={target.lat} lng={target.lng} />
                  <DisplacementRisk lat={target.lat} lng={target.lng} />
                </>
              )}
            </>
          )}
        </div>
      </div>

      {/* ── Drag divider ── */}
      <div
        onMouseDown={(e) => { dragging.current = true; e.preventDefault(); }}
        className="group relative flex w-2 flex-shrink-0 cursor-col-resize items-center justify-center bg-slate-200 transition-colors hover:bg-cyan/30 active:bg-cyan/50"
      >
        <div className="flex flex-col gap-[4px]">
          {[0, 1, 2, 3, 4].map((i) => (
            <span
              key={i}
              className="block h-1 w-1 rounded-full bg-slate-400 transition-colors group-hover:bg-cyan group-active:bg-cyan"
            />
          ))}
        </div>
      </div>

      {/* ── Right: Mapbox map fills remaining space ── */}
      <div className="h-screen min-w-0 flex-1">
        <MapView
          layer={target ? layer : 'city'}
          lat={target?.lat}
          lng={target?.lng}
          ccaId={context.cca?.id}
          tractGeoid={context.tract?.id}
        />
      </div>
    </div>
  );
}
