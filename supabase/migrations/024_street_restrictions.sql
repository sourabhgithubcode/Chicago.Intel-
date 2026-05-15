-- Snow route restrictions and winter overnight parking restriction street segments.

CREATE TABLE IF NOT EXISTS snow_route_restrictions (
  id               integer                      NOT NULL,
  on_street        text                         NOT NULL,
  from_street      text,
  to_street        text,
  restriction_type text,
  geometry         geometry(MultiLineString, 4326),
  PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS idx_snow_routes_geometry
  ON snow_route_restrictions USING GIST(geometry);

CREATE TABLE IF NOT EXISTS winter_overnight_restrictions (
  id               integer                      NOT NULL,
  on_street        text                         NOT NULL,
  from_street      text,
  to_street        text,
  restriction_type text,
  geometry         geometry(MultiLineString, 4326),
  PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS idx_winter_restrictions_geometry
  ON winter_overnight_restrictions USING GIST(geometry);
