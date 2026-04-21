-- Supabase RPC functions called by the frontend

-- Safety score for a given coordinate (0.25mi radius)
CREATE OR REPLACE FUNCTION safety_at_point(lat FLOAT, lng FLOAT)
RETURNS TABLE(violent_count INT, property_count INT, total_count INT)
LANGUAGE sql STABLE AS $$
  SELECT
    COUNT(*) FILTER (WHERE type = 'violent')::INT  AS violent_count,
    COUNT(*) FILTER (WHERE type = 'property')::INT AS property_count,
    COUNT(*)::INT                                   AS total_count
  FROM cpd_incidents
  WHERE ST_DWithin(
    location,
    ST_MakePoint(lng, lat)::geography,
    402  -- 0.25 miles in meters
  )
  AND date >= NOW() - INTERVAL '5 years';
$$;

-- Nearest CTA stop for a given coordinate
CREATE OR REPLACE FUNCTION nearest_cta(lat FLOAT, lng FLOAT)
RETURNS TABLE(stop_name TEXT, lines TEXT[], distance_m INT)
LANGUAGE sql STABLE AS $$
  SELECT
    name,
    lines,
    ST_Distance(location, ST_MakePoint(lng, lat)::geography)::INT AS distance_m
  FROM cta_stops
  ORDER BY location <-> ST_MakePoint(lng, lat)::geography
  LIMIT 1;
$$;

-- Nearest park for a given coordinate
CREATE OR REPLACE FUNCTION nearest_park(lat FLOAT, lng FLOAT)
RETURNS TABLE(park_name TEXT, distance_m INT, acreage NUMERIC)
LANGUAGE sql STABLE AS $$
  SELECT
    name,
    ST_Distance(location, ST_MakePoint(lng, lat)::geography)::INT AS distance_m,
    acreage
  FROM parks
  ORDER BY location <-> ST_MakePoint(lng, lat)::geography
  LIMIT 1;
$$;

-- Find building closest to a geocoded coordinate
CREATE OR REPLACE FUNCTION find_building_at(lat FLOAT, lng FLOAT)
RETURNS TABLE(
  pin TEXT, address TEXT, owner TEXT, year_built INT,
  tax_current BOOLEAN, tax_annual INT,
  violations_5yr INT, heat_complaints INT, bug_reports INT,
  landlord_score NUMERIC, flood_zone TEXT, school_elem TEXT,
  distance_m INT
)
LANGUAGE sql STABLE AS $$
  SELECT
    pin, address, owner, year_built,
    tax_current, tax_annual,
    violations_5yr, heat_complaints, bug_reports,
    landlord_score, flood_zone, school_elem,
    ST_Distance(location, ST_MakePoint(lng, lat)::geography)::INT AS distance_m
  FROM buildings
  WHERE ST_DWithin(location, ST_MakePoint(lng, lat)::geography, 100)
  ORDER BY location <-> ST_MakePoint(lng, lat)::geography
  LIMIT 1;
$$;

-- 311 complaints for a specific address (last 5 years)
CREATE OR REPLACE FUNCTION complaints_at_address(addr TEXT)
RETURNS TABLE(type TEXT, complaint_count BIGINT)
LANGUAGE sql STABLE AS $$
  SELECT type, COUNT(*) AS complaint_count
  FROM complaints_311
  WHERE address_norm ILIKE addr
  AND date >= NOW() - INTERVAL '5 years'
  GROUP BY type;
$$;
