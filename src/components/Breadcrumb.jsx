// Chicago › Neighborhood › Census Tract › Building — drill-down nav.
// Current level is plain text. Every level above current is always clickable
// (even when name isn't resolved yet — navigate the layer, show what we have).

const SEP = <span className="text-t3 select-none px-2 text-lg">›</span>;

export default function Breadcrumb({ layer, ccaName, tractId, address, onLayerChange }) {
  const levels = [
    { id: 'city',     label: 'Chicago' },
    { id: 'cca',      label: ccaName ?? 'Neighborhood' },
    { id: 'tract',    label: tractId  ?? 'Census Tract' },
    { id: 'building', label: address ? address.split(',')[0] : 'Building' },
  ];

  const currentIdx = levels.findIndex((l) => l.id === layer);

  return (
    <nav className="glass-2 px-4 py-3 flex flex-wrap items-center">
      {levels.map((lvl, i) => {
        const isCurrent = i === currentIdx;
        const isClickable = i !== currentIdx;

        return (
          <span key={lvl.id} className="flex items-center">
            {i > 0 && SEP}
            {isClickable ? (
              <button
                onClick={() => onLayerChange(lvl.id)}
                className="text-sm font-medium text-cyan hover:text-t0 transition-colors underline underline-offset-2"
              >
                {lvl.label}
              </button>
            ) : (
              <span
                className={
                  isCurrent
                    ? 'text-sm font-semibold text-t0'
                    : 'text-sm text-t3'
                }
              >
                {lvl.label}
              </span>
            )}
          </span>
        );
      })}
    </nav>
  );
}
