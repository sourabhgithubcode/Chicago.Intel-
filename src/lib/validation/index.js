// Every user input hits validation before being forwarded to an external API.
// Fail fast, fail cheap, fail with a typed error the UI can surface.

import { ValidationError, OutOfBoundsError } from '../errors/index.js';

export const CHICAGO_BOUNDS = {
  minLat: 41.6445,
  maxLat: 42.023,
  minLng: -87.9401,
  maxLng: -87.5237,
};

export function validateAddress(raw) {
  if (typeof raw !== 'string') throw new ValidationError({ meta: { raw } });
  const addr = raw.trim();
  if (addr.length < 5 || addr.length > 200) {
    throw new ValidationError({
      userMessage: 'Address looks too short or too long.',
      meta: { raw },
    });
  }
  return addr;
}

export function validateSalary(raw) {
  const n = Number(raw);
  if (!Number.isFinite(n) || n < 10_000 || n > 1_000_000) {
    throw new ValidationError({
      userMessage: 'Enter a salary between $10,000 and $1,000,000.',
      meta: { raw },
    });
  }
  return Math.round(n);
}

export function validateChicagoBounds({ lat, lng }) {
  const b = CHICAGO_BOUNDS;
  const inside =
    lat >= b.minLat && lat <= b.maxLat && lng >= b.minLng && lng <= b.maxLng;
  if (!inside) throw new OutOfBoundsError({ meta: { lat, lng } });
  return { lat, lng };
}

export function validateRent(raw) {
  const n = Number(raw);
  if (!Number.isFinite(n) || n < 200 || n > 20_000) {
    throw new ValidationError({
      userMessage: 'Enter a monthly rent between $200 and $20,000.',
      meta: { raw },
    });
  }
  return Math.round(n);
}

export function validateCost(raw, { min = 0, max = 10_000 } = {}) {
  const n = Number(raw);
  if (!Number.isFinite(n) || n < min || n > max) {
    throw new ValidationError({
      userMessage: `Enter a value between ${min} and ${max}.`,
      meta: { raw, min, max },
    });
  }
  return n;
}

export function sanitizeForUrl(s) {
  return String(s ?? '')
    .trim()
    .replace(/[^\w\s,.-]/g, '')
    .slice(0, 200);
}
