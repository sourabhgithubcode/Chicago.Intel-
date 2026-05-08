// Exponential backoff + circuit breaker. Every external API call goes through
// these so a flapping upstream cannot take the whole app down or burn our quota.

import { ExternalApiError, RateLimitError } from '../errors/index.js';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export async function withRetry(fn, opts = {}) {
  const {
    attempts = 3,
    baseMs = 400,
    factor = 2,
    jitter = 0.25,
    shouldRetry = (err) => !(err instanceof RateLimitError),
    onRetry,
  } = opts;

  let lastErr;
  for (let i = 0; i < attempts; i++) {
    try {
      return await fn();
    } catch (err) {
      lastErr = err;
      if (i === attempts - 1 || !shouldRetry(err)) break;
      const delay = baseMs * factor ** i * (1 + (Math.random() - 0.5) * jitter);
      onRetry?.({ attempt: i + 1, err, delay });
      await sleep(delay);
    }
  }
  throw lastErr;
}

export class CircuitBreaker {
  constructor({ name, failureThreshold = 5, cooldownMs = 30_000 } = {}) {
    this.name = name;
    this.failureThreshold = failureThreshold;
    this.cooldownMs = cooldownMs;
    this.failures = 0;
    this.openedAt = null;
  }

  get state() {
    if (this.openedAt === null) return 'closed';
    return Date.now() - this.openedAt > this.cooldownMs ? 'half-open' : 'open';
  }

  async fire(fn) {
    if (this.state === 'open') {
      throw new ExternalApiError({
        meta: { breaker: this.name, state: 'open' },
        userMessage: 'This service is temporarily unavailable.',
      });
    }
    try {
      const result = await fn();
      this.failures = 0;
      this.openedAt = null;
      return result;
    } catch (err) {
      this.failures += 1;
      if (this.failures >= this.failureThreshold) this.openedAt = Date.now();
      throw err;
    }
  }
}
