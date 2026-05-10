// Address search → geocode → parent receives {lat, lng, address}.
// First user-visible interaction in the app — keep it boring.

import { useState } from 'react';
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
    <form onSubmit={submit} className="glass-2 space-y-2 p-5">
      <label className="label-mono text-t2 block text-xs" htmlFor="addr">
        chicago address
      </label>
      <div className="flex gap-2">
        <input
          id="addr"
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="233 S Wacker Dr"
          className="glass-3 text-t0 placeholder-t3 flex-1 rounded-md px-3 py-2 outline-none focus:ring-1 focus:ring-cyan"
          autoComplete="off"
        />
        <button
          type="submit"
          disabled={busy || !query.trim()}
          className="glass-3 text-t0 rounded-md px-4 py-2 font-medium hover:bg-white/10 disabled:opacity-50"
        >
          {busy ? '…' : 'Search'}
        </button>
      </div>
      {err && <p className="text-rose text-xs">{err}</p>}
    </form>
  );
}
