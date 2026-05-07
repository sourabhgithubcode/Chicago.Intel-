-- Migration 011 — Per-run mode + watermark on pipeline_runs
--
-- Extends the pipeline_runs table from migration 005 to support the seed /
-- delta / on_view distinction (§12.8), the lookback-window mechanism (§12.7),
-- the per-source resume model (§12.1), the schema-drift audit trail (§12.6),
-- and the row-count instrumentation referenced in §12.1.
--
-- After this migration, the canonical pipeline_runs row is per-source per-run.
-- The pre-existing `sources TEXT[]` array stays for orchestrator-level
-- multi-source rollups but new fetcher code writes to the singular `source`.
--
-- Idempotent: ADD COLUMN IF NOT EXISTS / CREATE OR REPLACE / IF NOT EXISTS.

-- ─── 1. New columns on pipeline_runs ──────────────────
ALTER TABLE pipeline_runs
  ADD COLUMN IF NOT EXISTS source         TEXT,
  ADD COLUMN IF NOT EXISTS mode           TEXT,
  ADD COLUMN IF NOT EXISTS last_modified_high_watermark  TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS fetch_window_start            TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS fetch_window_end              TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS lookback_days                 INT,
  ADD COLUMN IF NOT EXISTS rows_in        INT DEFAULT 0,
  ADD COLUMN IF NOT EXISTS rows_upserted  INT DEFAULT 0,
  ADD COLUMN IF NOT EXISTS rows_skipped   INT DEFAULT 0,
  ADD COLUMN IF NOT EXISTS rows_tombstoned INT DEFAULT 0,
  ADD COLUMN IF NOT EXISTS schema_hash    TEXT;

-- ─── 2. mode CHECK constraint ─────────────────────────
-- Use a trigger-friendly CHECK that allows NULL during transition (existing
-- rows from migration 005 won't have a mode). New rows must specify it.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.table_constraints
    WHERE table_name = 'pipeline_runs' AND constraint_name = 'pipeline_runs_mode_check'
  ) THEN
    ALTER TABLE pipeline_runs
      ADD CONSTRAINT pipeline_runs_mode_check
      CHECK (mode IS NULL OR mode IN ('seed', 'delta', 'on_view'));
  END IF;
END$$;

-- ─── 3. Resume-state indexes ──────────────────────────
-- "What was the last successful delta run for source X?" is the hottest query
-- a fetcher makes — it drives the watermark read in §12.9 step 1–2.
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_resume
  ON pipeline_runs(source, mode, status, completed_at DESC);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_source_mode
  ON pipeline_runs(source, mode);

-- ─── 4. Resume-state helper function ──────────────────
-- Returns the resume context for the next run of a source. The fetcher
-- consumes this directly to compute its fetch window (§12.9 step 2).
--
-- last_modified_high_watermark = MAX across all prior successful runs (NULL on first run).
-- lookback_days                = configured lookback for this source (caller passes in).
-- next_window_start            = watermark - lookback (NULL → caller falls back to seed window).
DROP FUNCTION IF EXISTS get_resume_state(TEXT);
CREATE OR REPLACE FUNCTION get_resume_state(p_source TEXT)
RETURNS TABLE (
  last_run_id        TEXT,
  last_completed_at  TIMESTAMPTZ,
  last_high_watermark TIMESTAMPTZ,
  last_mode          TEXT,
  total_seed_runs    INT,
  total_delta_runs   INT
)
LANGUAGE sql STABLE AS $$
  WITH ranked AS (
    SELECT
      run_id, completed_at, last_modified_high_watermark, mode,
      ROW_NUMBER() OVER (ORDER BY completed_at DESC) AS rn
    FROM pipeline_runs
    WHERE source = p_source
      AND status = 'success'
      AND last_modified_high_watermark IS NOT NULL
  )
  SELECT
    (SELECT run_id FROM ranked WHERE rn = 1),
    (SELECT completed_at FROM ranked WHERE rn = 1),
    (SELECT MAX(last_modified_high_watermark)
       FROM pipeline_runs
      WHERE source = p_source AND status = 'success'),
    (SELECT mode FROM ranked WHERE rn = 1),
    (SELECT COUNT(*)::INT FROM pipeline_runs
       WHERE source = p_source AND mode = 'seed' AND status = 'success'),
    (SELECT COUNT(*)::INT FROM pipeline_runs
       WHERE source = p_source AND mode = 'delta' AND status = 'success');
$$;

-- ─── 5. View — most recent run per source (admin convenience) ──
-- Returns the latest run of any status per source. Useful in the orchestrator
-- dashboard / Supabase Studio to spot stalled sources.
CREATE OR REPLACE VIEW pipeline_runs_latest AS
SELECT DISTINCT ON (source)
  source, run_id, mode, status,
  started_at, completed_at,
  last_modified_high_watermark,
  fetch_window_start, fetch_window_end, lookback_days,
  rows_in, rows_upserted, rows_skipped, rows_tombstoned,
  schema_hash, error_message
FROM pipeline_runs
WHERE source IS NOT NULL
ORDER BY source, started_at DESC;

-- ─── Notes for fetcher authors ────────────────────────
-- Per §12.9 step 1–2, every fetcher's resume logic looks like:
--
--   resume = SELECT * FROM get_resume_state('cpd');
--   IF mode = 'seed' THEN
--     fetch_window_start := NOW() - INTERVAL '5 years';   -- §12.8 seed window
--   ELSIF resume.last_high_watermark IS NULL THEN
--     -- No prior delta run AND not seeding → refuse to start
--     RAISE EXCEPTION 'Source % has never been seeded; run with --mode seed first', p_source;
--   ELSE
--     fetch_window_start := resume.last_high_watermark - lookback_interval;  -- §12.7
--   END IF;
--   fetch_window_end := NOW();
--
-- The lookback_interval is config (e.g. 7 days for CPD/311, 30 for Assessor /
-- Treasurer) and is recorded in the new pipeline_runs.lookback_days column so
-- the audit trail captures what was actually applied.
