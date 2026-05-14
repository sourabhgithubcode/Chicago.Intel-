import { useState } from 'react';

export default function Tooltip({ children, content }) {
  const [show, setShow] = useState(false);

  return (
    <span
      className="relative inline-flex items-center"
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
    >
      {children}
      {show && (
        <span
          role="tooltip"
          className="pointer-events-none absolute bottom-full left-0 z-50 mb-2 w-max max-w-[220px] rounded-lg bg-slate-900 px-3 py-2 text-xs leading-snug text-white shadow-xl"
        >
          {content}
          <span className="absolute left-3 top-full border-4 border-transparent border-t-slate-900" />
        </span>
      )}
    </span>
  );
}
