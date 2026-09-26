-- CollectAI database roles and grants (specs/design/data-models.md section 1,
-- "Database roles"). Portfolio/demo project: synthetic data only.
--
-- Three roles:
--   collectai_owner    - runs migrations (E1-S3's Alembic migrations, and
--                         E1-S4's later audit_event migration) and owns every
--                         object. Connect as this role only to run
--                         `python -m collectai.bootstrap.cli migrate`.
--   collectai_app       - the application's runtime role. INSERT/SELECT/UPDATE
--                         on ordinary business tables; INSERT+SELECT only
--                         (no UPDATE, no DELETE) on the insert-only tables
--                         (payment_event, chat_message, review_decision, and
--                         later audit_event) so a compromised or buggy app
--                         process can never rewrite history.
--   collectai_readonly  - SELECT only, for reporting and evaluation reads.
--
-- No password is set here. This file is committed to version control and
-- must never contain a credential (CLAUDE.md: never introduce real
-- credentials). The deployment that runs this script (docker-compose /
-- E1-S5) sets each role's password afterwards via `ALTER ROLE ... PASSWORD`
-- from an environment variable or a docker secret, never a literal in SQL.
--
-- Idempotent: safe to re-run against a database where the roles already
-- exist (matches migrations' own "applies cleanly, re-runs without error"
-- requirement, AC5).
--
-- Two phases, one file (docker-compose.yml runs it twice):
--   1. At database initialisation, before any table exists (mounted into the
--      postgres image's /docker-entrypoint-initdb.d): creates the three
--      roles. The table grants below are skipped, because
--      `alembic_version` does not exist yet, and a GRANT on a missing table
--      would abort the whole initialisation.
--   2. After the migrations, as `collectai_owner` (the `grants` service, run
--      with ON_ERROR_STOP): `alembic_version` now exists, so every GRANT below
--      runs as a plain statement. A table that is missing or was renamed then
--      fails loudly; nothing is skipped silently.
-- The application role must not be used before phase 2 has succeeded: the
-- `api` service waits for the `grants` service, and GET /api/ready verifies
-- the resulting privileges (readiness check `app_role_grants`).

DO
$$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'collectai_owner') THEN
        CREATE ROLE collectai_owner LOGIN CREATEDB;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'collectai_app') THEN
        CREATE ROLE collectai_app LOGIN;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'collectai_readonly') THEN
        CREATE ROLE collectai_readonly LOGIN;
    END IF;
END
$$;

-- Phase 2 only: every statement below needs the migrated schema. The marker is
-- `alembic_version`, created by the first migration (in the same transaction as the tables).
DO
$grants$
BEGIN
    IF to_regclass('public.alembic_version') IS NULL THEN
        RAISE NOTICE 'init-roles: migrations not applied yet; roles ensured, table grants deferred';
        RETURN;
    END IF;

-- Ordinary business tables: collectai_app may INSERT, SELECT and UPDATE.
-- (audit_event is deliberately absent from every list below: it does not
-- exist until E1-S4's migration, which owns its own append-only grants.)
GRANT INSERT, SELECT, UPDATE ON TABLE
    customer,
    account,
    delinquency_record,
    delinquent_item,
    interaction,
    promise_to_pay,
    payment_arrangement,
    hardship_case,
    dispute,
    escalation_case,
    conversation,
    chat_turn,
    proposal,
    recommendation,
    policy_rule_set,
    demo_session,
    idempotency_record,
    clock_state,
    eval_run,
    eval_case_result
TO collectai_app;

-- Insert-only tables (data-models.md's own per-entity notes: "Insert-only",
-- "No UPDATE or DELETE grant to the application role"): collectai_app may
-- INSERT and SELECT, never UPDATE or DELETE.
GRANT INSERT, SELECT ON TABLE
    payment_event,
    chat_message,
    review_decision
TO collectai_app;

-- Reporting/evaluation role: SELECT only, on every business table.
GRANT SELECT ON TABLE
    customer,
    account,
    delinquency_record,
    delinquent_item,
    interaction,
    promise_to_pay,
    payment_event,
    payment_arrangement,
    hardship_case,
    dispute,
    escalation_case,
    review_decision,
    conversation,
    chat_message,
    chat_turn,
    proposal,
    recommendation,
    policy_rule_set,
    demo_session,
    idempotency_record,
    clock_state,
    eval_run,
    eval_case_result
TO collectai_readonly;

-- Sequences backing SERIAL/IDENTITY/bigint-identity primary keys (e.g.
-- idempotency_record.idempotency_id, audit_event.sequence once E1-S4 adds
-- it) need USAGE for collectai_app to insert; readonly needs none.
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO collectai_app;
END
$grants$;
