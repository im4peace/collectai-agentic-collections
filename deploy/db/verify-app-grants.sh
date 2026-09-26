#!/usr/bin/env bash
# Checks, against the running database, that the table grants really work for the application
# and read-only roles: what they may do succeeds, and what least privilege forbids is refused.
# Used by the `docker-smoke` CI job. Run it inside the db container (the image's local socket
# is trust-authenticated, so no password is needed):
#
#   docker compose exec -T db bash -s < deploy/db/verify-app-grants.sh
#
# Every statement carries `WHERE false` (or is a no-op), so nothing is ever changed: PostgreSQL
# checks privileges before it looks at rows. Exits non-zero if any expectation fails.

set -uo pipefail

DB="${POSTGRES_DB:-collectai}"
failures=0

psql_as() { # role sql
  psql -X -q -At -v ON_ERROR_STOP=1 -U "$1" -d "$DB" -c "$2" 2>&1
}

expect_allowed() { # role label sql
  if out=$(psql_as "$1" "$3"); then
    echo "ok      $1 may: $2"
  else
    echo "FAILED  $1 should be allowed to: $2"
    echo "        $out"
    failures=$((failures + 1))
  fi
}

expect_denied() { # role label sql
  if out=$(psql_as "$1" "$3"); then
    echo "FAILED  $1 must NOT be allowed to: $2"
    failures=$((failures + 1))
  elif grep -Eq "permission denied|must be owner" <<<"$out"; then
    echo "ok      $1 is denied: $2"
  else
    echo "FAILED  $1: $2 failed, but not with a privilege error:"
    echo "        $out"
    failures=$((failures + 1))
  fi
}

# --- collectai_app: the application role --------------------------------------------------
expect_allowed collectai_app "SELECT on customer" "SELECT count(*) FROM customer"
expect_allowed collectai_app "UPDATE on customer" "UPDATE customer SET customer_id = customer_id WHERE false"
expect_allowed collectai_app "INSERT on payment_event" "INSERT INTO payment_event SELECT * FROM payment_event WHERE false"
expect_allowed collectai_app "SELECT on audit_event" "SELECT count(*) FROM audit_event"

expect_denied collectai_app "DELETE on customer" "DELETE FROM customer WHERE false"
expect_denied collectai_app "UPDATE on payment_event" "UPDATE payment_event SET amount = amount WHERE false"
expect_denied collectai_app "DELETE on payment_event" "DELETE FROM payment_event WHERE false"
expect_denied collectai_app "UPDATE on audit_event" "UPDATE audit_event SET event_type = event_type WHERE false"
expect_denied collectai_app "DELETE on audit_event" "DELETE FROM audit_event WHERE false"
expect_denied collectai_app "DROP TABLE customer" "DROP TABLE customer"

# --- collectai_readonly: reporting role -------------------------------------------------------
expect_allowed collectai_readonly "SELECT on customer" "SELECT count(*) FROM customer"
expect_denied collectai_readonly "INSERT on customer" "INSERT INTO customer SELECT * FROM customer WHERE false"
expect_denied collectai_readonly "UPDATE on customer" "UPDATE customer SET customer_id = customer_id WHERE false"
expect_denied collectai_readonly "SELECT on audit_event" "SELECT count(*) FROM audit_event"

# --- the seed data really is there (the migrate service ran, and the app can read it) -------
customers=$(psql_as collectai_app "SELECT count(*) FROM customer") || customers=0
if [ "${customers:-0}" -gt 0 ] 2>/dev/null; then
  echo "ok      seeded customers visible to collectai_app: $customers"
else
  echo "FAILED  no seeded customers visible to collectai_app (got: ${customers:-none})"
  failures=$((failures + 1))
fi

if [ "$failures" -gt 0 ]; then
  echo "$failures grant expectation(s) failed"
  exit 1
fi
echo "all grant expectations hold"
