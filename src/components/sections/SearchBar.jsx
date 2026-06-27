// Address search with live autocomplete via the Mapbox Search JS SDK.
// <SearchBox> renders its own input + suggestion dropdown (debounce, keyboard
// nav, session handling are built in). Selecting a suggestion returns the
// coordinates directly, so we skip a separate geocode round-trip.
// Caller: App.jsx (onResult({ lat, lng, address })).

import { useState } from 'react';
import { SearchBox } from '@mapbox/search-js-react';

const TOKEN = import.meta.env.VITE_MAPBOX_TOKEN;
// Chicago bounding box [minLng, minLat, maxLng, maxLat] — keep results in-city.
const CHI_BBOX = [-87.940, 41.644, -87.524, 42.023];

export default function SearchBar({ onResult, initialValue = '' }) {
  const [value, setValue] = useState(initialValue);

  function handleRetrieve(res) {
    const f = res?.features?.[0];
    if (!f?.geometry?.coordinates) return;
    const [lng, lat] = f.geometry.coordinates;
    const address = f.properties?.full_address || f.properties?.name || value;
    onResult({ lat, lng, address });
  }

  return (
    <div className="glass-2 space-y-2 p-4">
      <label className="label-mono text-t3 block text-xs">chicago address</label>
      {TOKEN ? (
        <SearchBox
          accessToken={TOKEN}
          value={value}
          onChange={(d) => setValue(d)}
          onRetrieve={handleRetrieve}
          placeholder="233 S Wacker Dr"
          options={{
            language: 'en',
            country: 'US',
            bbox: CHI_BBOX,
            proximity: [-87.65, 41.85],
            types: 'address',
          }}
          theme={{
            variables: {
              colorPrimary: '#06b6d4',
              borderRadius: '0.375rem',
              fontFamily: 'inherit',
              unit: '14px',
            },
          }}
        />
      ) : (
        <p className="text-rose text-xs">
          Search unavailable — VITE_MAPBOX_TOKEN not set.
        </p>
      )}
    </div>
  );
}
