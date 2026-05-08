import NearestCTAStop from './components/sections/NearestCTAStop.jsx';

// Hardcoded test coord (Willis Tower) — replaced by SearchBar/geocoder later.
const TEST_LAT = 41.8789;
const TEST_LNG = -87.6359;

export default function App() {
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
          <div className="label-mono text-t3 pt-2">
            test address: Willis Tower ({TEST_LAT}, {TEST_LNG})
          </div>
        </header>

        <NearestCTAStop lat={TEST_LAT} lng={TEST_LNG} />
      </div>
    </main>
  );
}
