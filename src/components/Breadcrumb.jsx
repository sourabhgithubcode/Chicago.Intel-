// Chicago › [CCA] › [Tract] › [Address] drill-down nav.
// Current level is plain text; levels above are clickable buttons.

const SEP = <span className="text-t3 select-none mx-1">›</span>;

export default function Breadcrumb({ layer, ccaName, tractId, address, onLayerChange }) {
  const levels = [
    { id: 'city',     label: 'Chicago' },
    { id: 'cca',      label: ccaName ?? '—' },
    { id: 'tract',    label: tractId  ?? '—' },
    { id: 'building', label: address  ?? '—' },
  ];

  const currentIdx = levels.findIndex((l) => l.id === layer);

  return (
    <nav className="flex flex-wrap items-center gap-0 label-mono text-xs text-t2">
      {levels.map((lvl, i) => {
        const isCurrent = i === currentIdx;
        const isClickable = i < currentIdx && lvl.label !== '—';

        return (
          <span key={lvl.id} className="flex items-center">
            {i > 0 && SEP}
            {isClickable ? (
              <button
                onClick={() => onLayerChange(lvl.id)}
                className="text-cyan hover:text-t0 transition-colors"
              >
                {lvl.label}
              </button>
            ) : (
              <span className={isCurrent ? 'text-t0' : 'text-t3'}>
                {lvl.label}
              </span>
            )}
          </span>
        );
      })}
    </nav>
  );
}
