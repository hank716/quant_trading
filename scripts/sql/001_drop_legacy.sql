-- Phase 11: drop legacy tables no longer used after Qlib cutover.
-- Run this ONCE against the production Supabase database.
-- Backup first: pg_dump $DATABASE_URL > backup_before_phase11.sql

DROP TABLE IF EXISTS daily_reports_index CASCADE;
DROP TABLE IF EXISTS daily_trades CASCADE;
DROP TABLE IF EXISTS daily_positions CASCADE;
DROP TABLE IF EXISTS daily_candidates CASCADE;
DROP TABLE IF EXISTS model_promotions CASCADE;
DROP TABLE IF EXISTS model_versions CASCADE;
DROP TABLE IF EXISTS run_artifacts CASCADE;
DROP TABLE IF EXISTS run_steps CASCADE;
DROP TABLE IF EXISTS pipeline_runs CASCADE;
