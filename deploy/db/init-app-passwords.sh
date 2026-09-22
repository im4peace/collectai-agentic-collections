#!/bin/sh
# Runs after init-roles.sql (docker-compose.yml mounts this second, as
# `02-init-app-passwords.sh`) inside the official postgres image's
# `/docker-entrypoint-initdb.d/` on first container start only.
#
# init-roles.sql (E1-S3) deliberately creates the three collectai_* roles
# with no password ("the deployment that runs this script sets each role's
# password afterwards via ALTER ROLE ... PASSWORD from an environment
# variable ... never a literal in SQL" -- see that file's header comment).
# This script is that step: it reads the synthetic passwords from the `db`
# service's own environment (set from `.env`, never hard-coded here) and
# also grants `collectai_owner` the schema privileges Postgres 15+ no longer
# gives non-owner roles by default (`REVOKE ALL ON SCHEMA public FROM
# PUBLIC` is the modern default), so `collectai_owner` can actually run
# migrations against a database it did not create.
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    ALTER ROLE collectai_owner WITH PASSWORD '$COLLECTAI_OWNER_PASSWORD';
    ALTER ROLE collectai_app WITH PASSWORD '$COLLECTAI_APP_PASSWORD';
    ALTER ROLE collectai_readonly WITH PASSWORD '$COLLECTAI_READONLY_PASSWORD';
    GRANT ALL ON SCHEMA public TO collectai_owner;
    GRANT USAGE ON SCHEMA public TO collectai_app, collectai_readonly;
EOSQL
