// Typed error hierarchy. Every API + DB call throws one of these,
// never a generic Error. ErrorBoundary and monitoring route on .name.

class AppError extends Error {
  constructor(message, { cause, userMessage, meta } = {}) {
    super(message);
    this.name = this.constructor.name;
    this.cause = cause;
    this.userMessage = userMessage ?? 'Something went wrong.';
    this.meta = meta ?? {};
  }
}

export class GeocodeError extends AppError {
  constructor(opts) {
    super('Could not geocode address', {
      userMessage: 'We could not find that address in Chicago.',
      ...opts,
    });
  }
}

export class OutOfBoundsError extends AppError {
  constructor(opts) {
    super('Coordinate outside Chicago bounds', {
      userMessage: 'That address is outside our Chicago coverage area.',
      ...opts,
    });
  }
}

export class DatabaseError extends AppError {
  constructor(opts) {
    super('Database query failed', {
      userMessage: 'We had trouble loading data. Please retry.',
      ...opts,
    });
  }
}

export class BuildingNotFoundError extends AppError {
  constructor(opts) {
    super('No building match for coordinate', {
      userMessage: 'No building record found at that address yet.',
      ...opts,
    });
  }
}

export class RateLimitError extends AppError {
  constructor(opts) {
    super('External API rate limit hit', {
      userMessage: 'Too many requests — try again in a moment.',
      ...opts,
    });
  }
}

export class ExternalApiError extends AppError {
  constructor(opts) {
    super('External API failed', {
      userMessage: 'An upstream service is unavailable right now.',
      ...opts,
    });
  }
}

export class ValidationError extends AppError {
  constructor(opts) {
    super('Input validation failed', {
      userMessage: 'That input looks invalid — please check and retry.',
      ...opts,
    });
  }
}

export class DataQualityError extends AppError {
  constructor(opts) {
    super('Data failed quality checks', {
      userMessage: 'This record has a known data-quality issue.',
      ...opts,
    });
  }
}

export class QueryTooBroadError extends AppError {
  constructor(opts) {
    super('Query radius or result set exceeds safe bounds', {
      userMessage: 'That query is too broad — please narrow the area.',
      ...opts,
    });
  }
}
