import { useCallback, useState } from 'react';
import BuildingDetail from './components/sections/BuildingDetail.jsx';
import DisplacementRisk from './components/sections/DisplacementRisk.jsx';
import NearestCTAStop from './components/sections/NearestCTAStop.jsx';
import SearchBar from './components/sections/SearchBar.jsx';
import TaxBill from './components/sections/TaxBill.jsx';

// Default coord: Willis Tower. Used until the user runs their first search.
const DEFAULT = {
  lat: 41.8789,
  lng: -87.6359,
  address: '233 S Wacker Dr (default)',
};

export default function App() {
  const [target, setTarget] = useState(DEFAULT);
  const [pin, setPin] = useState(null);

  const handleBuildingLoaded = useCallback((b) => {
    setPin(b?.pin ?? null);
  }, []);

  return (
    <main className="relative min-h-screen overflow-hidden bg-bg">
      <div
        aria-hidden
        className="pointer-events-none fixed inset-0 z-0"
        style={{
          background:
            'radial-gradient(40vw 40vw at 15% 20%, rgba(168,255,120,0.12), transparent 60%),' +
            'radial-gradient(45vw 45vw at 85% 30%, rgba(56,189,248,0.12), transparent 60%),' +
            'radial-gradient(50vw 50vw at 50% 90%, rgba(192,132,252,0.10), transparent 60%)',
        }}
      />

      <div className="relative z-10 mx-auto flex min-h-screen max-w-3xl flex-col items-stretch gap-6 p-8">
        <header className="glass-1 space-y-3 p-8 text-center">
          <div className="label-mono text-t2">chicago · intel · v2</div>
          <h1 className="display text-5xl text-t0">Chicago.Intel</h1>
          <p className="text-t1 leading-relaxed">
            Neighborhood intelligence for Chicago renters. Show the data, show
            the source, show the confidence. Never tell anyone where to live.
          </p>
        </header>

        <SearchBar onResult={setTarget} />

        <div className="label-mono text-t3 text-center text-xs">
          {target.address}
        </div>

        <BuildingDetail
          lat={target.lat}
          lng={target.lng}
          onLoaded={handleBuildingLoaded}
        />
        <TaxBill pin={pin} />
        <NearestCTAStop lat={target.lat} lng={target.lng} />
        <DisplacementRisk lat={target.lat} lng={target.lng} />
      </div>
    </main>
  );
}
