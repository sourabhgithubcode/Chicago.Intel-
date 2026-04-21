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

      <div className="relative z-10 flex min-h-screen items-center justify-center p-8">
        <div className="glass-1 max-w-xl space-y-5 p-10 text-center">
          <div className="label-mono text-t2">chicago · intel · v2</div>

          <h1 className="display text-5xl text-t0">Chicago.Intel</h1>

          <p className="text-t1 leading-relaxed">
            Neighborhood intelligence for Chicago renters. Show the data, show
            the source, show the confidence. Never tell anyone where to live.
          </p>

          <div className="flex justify-center gap-2 pt-2">
            <span className="glass-3 label-mono px-3 py-1.5 text-lime">
              scaffold
            </span>
            <span className="glass-3 label-mono px-3 py-1.5 text-cyan">
              supabase
            </span>
            <span className="glass-3 label-mono px-3 py-1.5 text-violet">
              mapbox
            </span>
          </div>
        </div>
      </div>
    </main>
  );
}
