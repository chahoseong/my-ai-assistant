#!/usr/bin/env bash
set -euo pipefail

: "${POSTGRES_EXPORTER_PASSWORD:?POSTGRES_EXPORTER_PASSWORD must be set}"

# The official PostgreSQL image runs this init script only for an empty PGDATA.
# Existing local volumes can run this script explicitly to reconcile this role.
psql -v ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --set=exporter_password="$POSTGRES_EXPORTER_PASSWORD" <<'SQL'
SELECT format(
  'CREATE ROLE %I LOGIN PASSWORD %L',
  'postgres_exporter',
  :'exporter_password'
)
WHERE NOT EXISTS (
  SELECT 1 FROM pg_roles WHERE rolname = 'postgres_exporter'
)
\gexec

ALTER ROLE postgres_exporter WITH
  LOGIN
  NOSUPERUSER
  NOCREATEDB
  NOCREATEROLE
  NOREPLICATION
  NOBYPASSRLS
  PASSWORD :'exporter_password';

GRANT pg_monitor TO postgres_exporter;
GRANT CONNECT ON DATABASE assistant_dev TO postgres_exporter;
SQL
