import { Building, Building2, Globe2, Map } from 'lucide-react';

const LEVEL_ICONS = {
  city:     Globe2,
  cca:      Building,
  tract:    Map,
  building: Building2,
};

const SEP = <span className="text-t3 select-none px-2 text-base">›</span>;

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
        const Icon = LEVEL_ICONS[lvl.id];

        return (
          <span key={lvl.id} className="flex items-center">
            {i > 0 && SEP}
            {isClickable ? (
              <button
                onClick={() => onLayerChange(lvl.id)}
                className="flex items-center gap-1 text-sm font-medium text-cyan hover:text-t0 transition-colors underline underline-offset-2"
              >
                <Icon size={13} />
                {lvl.label}
              </button>
            ) : (
              <span className="flex items-center gap-1 text-sm font-semibold text-t0">
                <Icon size={13} />
                {lvl.label}
              </span>
            )}
          </span>
        );
      })}
    </nav>
  );
}
