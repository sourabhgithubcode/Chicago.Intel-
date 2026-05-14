import { useState } from 'react';
import { Search } from 'lucide-react';
import { geocodeAddress } from '../../lib/api/geocode.js';

export default function SearchBar({ onResult, initialValue = '' }) {
  const [query, setQuery] = useState(initialValue);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  async function submit(e) {
    e.preventDefault();
    if (!query.trim() || busy) return;
    setBusy(true);
    setErr(null);
    try {
      const hit = await geocodeAddress(query);
      if (!hit) {
        setErr('No match for that address in Chicago.');
        return;
      }
      onResult({ lat: hit.lat, lng: hit.lng, address: hit.formatted_address });
    } catch (e) {
      setErr(e.message ?? 'Geocode failed.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="glass-2 space-y-2 p-4">
      <label className="label-mono text-t3 block text-xs" htmlFor="addr">
        chicago address
      </label>
      <div className="flex gap-2">
        <input
          id="addr"
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="233 S Wacker Dr"
          className="glass-3 text-t0 placeholder:text-t3 flex-1 rounded-md px-3 py-2 text-sm outline-none transition-colors hover:border-slate-300 focus:ring-2 focus:ring-cyan/40"
          autoComplete="off"
        />
        <button
          type="submit"
          disabled={busy || !query.trim()}
          className="flex items-center gap-1.5 rounded-md bg-cyan px-4 py-2 text-sm font-semibold text-white transition-all hover:bg-blue-700 active:scale-95 disabled:opacity-40"
        >
          <Search size={14} />
          {busy ? 'Searching…' : 'Search'}
        </button>
      </div>
      {err && <p className="text-rose text-xs">{err}</p>}
    </form>
  );
}
