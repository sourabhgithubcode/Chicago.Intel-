import { AlertTriangle, Shield, ShieldCheck } from 'lucide-react';

// Confidence badge — every data point in the UI must carry one.
// Color encodes the trust band documented in CLAUDE.md:
//   9–10/10 → lime  (verifiable in <5min)
//   7–8/10  → cyan  (strong source, minor caveats)
//   ≤6/10   → amber (directional / signal-only)

const bandFor = (n) => {
  if (n >= 9) return { color: 'text-lime',  Icon: ShieldCheck,    label: 'verified' };
  if (n >= 7) return { color: 'text-cyan',  Icon: Shield,         label: 'strong'   };
  return            { color: 'text-amber', Icon: AlertTriangle,  label: 'signal'   };
};

export default function ConfidenceTag({ score, source }) {
  const { color, Icon, label } = bandFor(score);
  return (
    <span
      className={`glass-3 label-mono inline-flex items-center gap-1.5 px-2.5 py-1 ${color}`}
      title={source ? `Source: ${source.label}` : undefined}
    >
      <Icon size={11} />
      <span>{score}/10</span>
      <span className="text-t3">·</span>
      <span>{label}</span>
      {source && (
        <>
          <span className="text-t3">·</span>
          {source.url ? (
            <a
              href={source.url}
              target="_blank"
              rel="noreferrer"
              className="text-t1 hover:text-t0 underline-offset-2 hover:underline"
            >
              {source.label}
            </a>
          ) : (
            <span className="text-t1">{source.label}</span>
          )}
        </>
      )}
    </span>
  );
}
