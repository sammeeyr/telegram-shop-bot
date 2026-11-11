#!/bin/sh
set -eu

psql --set=ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set=runtime_password="$COMMERCE_RUNTIME_PASSWORD" <<'SQL'
CREATE ROLE commerce_runtime LOGIN PASSWORD :'runtime_password' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
GRANT CONNECT ON DATABASE commerce TO commerce_runtime;
GRANT USAGE ON SCHEMA public TO commerce_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO commerce_runtime;
ALTER DEFAULT PRIVILEGES FOR ROLE commerce_migrator IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO commerce_runtime;
SQL