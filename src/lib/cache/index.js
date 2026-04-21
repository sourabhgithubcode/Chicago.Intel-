// LRU cache with TTL. Used everywhere an API call could be cached to stay
// within free tiers. Pre-configured instances below match the caching
// strategy described in each API's comment in src/lib/api/*.

class LRU {
  constructor({ max = 500, ttlMs } = {}) {
    this.max = max;
    this.ttlMs = ttlMs;
    this.map = new Map();
  }

  _isExpired(entry) {
    return this.ttlMs && Date.now() - entry.t > this.ttlMs;
  }

  get(key) {
    const entry = this.map.get(key);
    if (!entry) return undefined;
    if (this._isExpired(entry)) {
      this.map.delete(key);
      return undefined;
    }
    this.map.delete(key);
    this.map.set(key, entry);
    return entry.v;
  }

  set(key, value) {
    if (this.map.has(key)) this.map.delete(key);
    this.map.set(key, { v: value, t: Date.now() });
    if (this.map.size > this.max) {
      const oldest = this.map.keys().next().value;
      this.map.delete(oldest);
    }
  }

  clear() {
    this.map.clear();
  }
}

const HOUR = 60 * 60 * 1000;
const DAY = 24 * HOUR;

export const geocodeCache = new LRU({ max: 2000, ttlMs: DAY });
export const buildingCache = new LRU({ max: 500, ttlMs: HOUR });
export const amenityCache = new LRU({ max: 500, ttlMs: 30 * 60 * 1000 });
export const neighborhoodCache = new LRU({ max: 100, ttlMs: HOUR });

export { LRU };
