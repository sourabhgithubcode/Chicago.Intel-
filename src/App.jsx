import { useCallback, useEffect, useRef, useState } from 'react';
import Breadcrumb from './components/Breadcrumb.jsx';
import MapView from './components/MapView.jsx';
import BuildingDetail from './components/sections/BuildingDetail.jsx';
import CcaOverview from './components/sections/CcaOverview.jsx';
import DisplacementRisk from './components/sections/DisplacementRisk.jsx';
import NearestCTAStop from './components/sections/NearestCTAStop.jsx';
import SearchBar from './components/sections/SearchBar.jsx';
import TaxBill from './components/sections/TaxBill.jsx';
import { getCcaAt, getTractAt } from './lib/api/supabase.js';

const DEFAULT = {
  lat: 41.8789,
  lng: -87.6359,
  address: '233 S Wacker Dr (default)',
  zip: null,
};

export default function App() {
  const [target, setTarget] = useState(DEFAULT);
  const [pin, setPin] = useState(null);
  const [layer, setLayer] = useState('building');
  const [context, setContext] = useState({ cca: null, tract: null });
  const [splitPct, setSplitPct] = useState(50);
  const dragging = useRef(false);
  const containerRef = useRef(null);

  useEffect(() => {
    const onMove = (e) => {
      if (!dragging.current || !containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const pct = Math.min(Math.max(((e.clientX - rect.left) / rect.width) * 100, 25), 75);
      setSplitPct(pct);
    };
    const onUp = () => { dragging.current = false; };
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

  return (
    <div ref={containerRef} className="flex h-screen overflow-hidden bg-bg select-none">
      {/* ── Left: scrollable data panel ── */}
      <div style={{ width: `${splitPct}%` }} className="flex-shrink-0 overflow-y-auto">
        <div className="flex flex-col gap-4 p-6">
          <header className="glass-1 space-y-2 p-6 text-center">
            <div className="label-mono text-t2 text-xs">chicago · intel · v2</div>
            <h1 className="display text-4xl text-t0">Chicago.Intel</h1>
            <p className="text-t2 text-sm leading-relaxed">
              Neighborhood intelligence for Chicago renters.
            </p>
          </header>

          <Breadcrumb
            layer={layer}
            ccaName={context.cca?.name}
            tractId={context.tract?.id}
            address={target.address !== DEFAULT.address ? target.address : null}
            onLayerChange={setLayer}
          />

          <SearchBar onResult={handleResult} />

          {/* ── Layer-specific data sections ── */}
          {layer === 'city' && (
            <p className="text-t2 text-sm text-center py-8">
              Search an address above to explore building-level intelligence.
            </p>
          )}

          {layer === 'cca' && (
            <CcaOverview ccaId={context.cca?.id} />
          )}

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
                onLoaded={handleBuildingLoaded}
              />
              <TaxBill pin={pin} />
              <NearestCTAStop lat={target.lat} lng={target.lng} />
              <DisplacementRisk lat={target.lat} lng={target.lng} />
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

      {/* ── Right: sticky Mapbox map ── */}
      <div style={{ width: `${100 - splitPct}%` }} className="h-screen flex-shrink-0">
        <MapView
          layer={layer}
          lat={target.lat}
          lng={target.lng}
          ccaId={context.cca?.id}
          tractGeoid={context.tract?.id}
        />
      </div>
    </div>
  );
}
