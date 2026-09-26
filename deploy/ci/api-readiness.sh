#!/usr/bin/env bash
# CI helper for the `docker-smoke` and `e2e` jobs: wait for the API to report ready, or check its
# health and readiness once, and when that fails say WHY instead of only exiting non-zero.
#
#   bash deploy/ci/api-readiness.sh wait    # poll GET /api/ready until 200 (default 180 s)
#   bash deploy/ci/api-readiness.sh check   # GET /api/health once, then GET /api/ready once
#
# Run from the repository root. Environment (all optional):
#   COMPOSE_CMD   the compose command, e.g. "docker compose -f a.yml -f b.yml" (default
#                 "docker compose", which honours COMPOSE_FILE)
#   API_URL       default http://localhost:8000
#   WAIT_SECONDS  default 180 ("wait" only)      POLL_SECONDS  default 3 ("wait" only)
#
# A failure is reported as one of:
#   - API unavailable (connection refused, timeout: curl itself failed)
#   - a non-2xx HTTP response (the body, normally the readiness JSON, is printed)
#   - HTTP 2xx whose readiness body reports a failed check, or lacks `app_role_grants`
#   - an empty or malformed body
# and is followed by `docker compose ps` and the last log lines of the api, db, migrate and
# grants services. Nothing else is printed: no environment, no compose configuration.
# curl's exit status is captured on its own (never through a pipe), so it cannot be hidden.

set -uo pipefail

API_URL="${API_URL:-http://localhost:8000}"
WAIT_SECONDS="${WAIT_SECONDS:-180}"
POLL_SECONDS="${POLL_SECONDS:-3}"
read -r -a COMPOSE <<<"${COMPOSE_CMD:-docker compose}"

BODY="$(mktemp)"
trap 'rm -f "$BODY"' EXIT
HTTP_CODE=000
CURL_RC=0

fetch() { # path -> HTTP_CODE, CURL_RC and the response body in $BODY
  : >"$BODY"
  CURL_RC=0
  HTTP_CODE=$(curl -s -o "$BODY" -w '%{http_code}' --max-time 10 "$API_URL$1") || CURL_RC=$?
}

# Empty when the last fetch is a 2xx response, otherwise a one-line reason.
transport_problem() {
  if [ "$CURL_RC" -ne 0 ]; then
    echo "API unavailable: curl exit $CURL_RC (connection refused or timed out), HTTP status $HTTP_CODE"
  elif [[ ! "$HTTP_CODE" =~ ^2[0-9][0-9]$ ]]; then
    echo "non-2xx HTTP response: $HTTP_CODE"
  fi
}

show_body() {
  echo "--- response body (HTTP $HTTP_CODE, first 4000 bytes):"
  head -c 4000 "$BODY"
  echo
  echo "--- end of response body"
}

diagnostics() {
  echo "::group::docker compose ps -a"
  "${COMPOSE[@]}" ps -a
  echo "::endgroup::"
  local service
  for service in api db migrate grants; do
    echo "::group::docker compose logs ($service, last 200 lines)"
    "${COMPOSE[@]}" logs --no-color --tail=200 "$service"
    echo "::endgroup::"
  done
}

give_up() { # message
  echo "::error::$1"
  show_body
  diagnostics
  exit 1
}

wait_for_ready() {
  local deadline=$((SECONDS + WAIT_SECONDS))
  while [ "$SECONDS" -lt "$deadline" ]; do
    fetch /api/ready
    if [ "$CURL_RC" -eq 0 ] && [ "$HTTP_CODE" = 200 ]; then
      echo "API reported ready"
      return 0
    fi
    sleep "$POLL_SECONDS"
  done
  local reason
  reason="$(transport_problem)"
  give_up "API did not report ready within ${WAIT_SECONDS}s. Last attempt: ${reason:-HTTP $HTTP_CODE}"
}

check_health_and_readiness() {
  local reason
  fetch /api/health
  reason="$(transport_problem)"
  [ -z "$reason" ] || give_up "GET /api/health: $reason"
  echo "GET /api/health -> HTTP $HTTP_CODE: $(head -c 500 "$BODY")"

  fetch /api/ready
  reason="$(transport_problem)"
  [ -z "$reason" ] || give_up "GET /api/ready: $reason"
  echo "GET /api/ready -> HTTP $HTTP_CODE"
  cat "$BODY"
  echo

  local rc=0
  python3 - "$BODY" <<'PY' || rc=$?
import json
import sys

raw = open(sys.argv[1], encoding="utf-8").read()
try:
    body = json.loads(raw)
except ValueError as error:
    print(f"malformed or empty readiness response: {error}")
    sys.exit(2)
checks = body.get("checks") if isinstance(body, dict) else None
if not isinstance(checks, list) or not all(isinstance(c, dict) for c in checks):
    print("malformed readiness response: no list of checks")
    sys.exit(2)
failed = [c.get("name") for c in checks if not c.get("ok")]
if body.get("status") != "ready" or failed:
    print(f"readiness body reports status={body.get('status')!r}, failed checks: {failed}")
    sys.exit(3)
if not any(c.get("name") == "app_role_grants" for c in checks):
    print("readiness body has no app_role_grants check")
    sys.exit(3)
print("readiness body: status ready, every check ok, app_role_grants present")
PY
  case "$rc" in
    0) ;;
    2) give_up "GET /api/ready: empty or malformed response body" ;;
    3) give_up "GET /api/ready: HTTP $HTTP_CODE but the readiness body reports a failed check" ;;
    *) give_up "GET /api/ready: could not evaluate the readiness body (python3 exit $rc)" ;;
  esac
}

case "${1:-}" in
  wait) wait_for_ready ;;
  check) check_health_and_readiness ;;
  *)
    echo "usage: $0 wait|check" >&2
    exit 2
    ;;
esac
