-- Migration 016 — Allow 'bronze_only' in pipeline_runs.mode
--
-- The orchestrator's --bronze-only flag writes a per-source pipeline_runs row
-- so the frontend's "synced X ago" UI (getLastSyncedAt) can show a real
-- timestamp even when silver upsert is skipped. That row's mode column needs
-- to accept 'bronze_only', which migration 011's CHECK constraint rejects.
--
-- Idempotent: drops the existing CHECK constraint if present, then re-adds it
-- with the widened allow-list. Same DO $$ pattern as migration 011 step 2.

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.table_constraints
    WHERE table_name = 'pipeline_runs' AND constraint_name = 'pipeline_runs_mode_check'
  ) THEN
    ALTER TABLE pipeline_runs DROP CONSTRAINT pipeline_runs_mode_check;
  END IF;

  ALTER TABLE pipeline_runs
    ADD CONSTRAINT pipeline_runs_mode_check
    CHECK (mode IS NULL OR mode IN ('seed', 'delta', 'on_view', 'bronze_only'));
END$$;
