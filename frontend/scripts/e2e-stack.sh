#!/usr/bin/env bash
# e2e-stack.sh — bring up the ISOLATED backend/MySQL/MailHog stack that
# Playwright runs against, with synthetic demo data only.
#
# This NEVER touches the developer's day-to-day "me" compose project (real
# club data, ports 8000/3306/8025). It always targets its own compose
# project name ("trocha-e2e" by default) and its own host ports, defined in
# ../docker-compose.e2e.yml.
#
# Usage (run from anywhere; the script cd's to the repo root itself):
#   frontend/scripts/e2e-stack.sh up       # build, start, wait for health + seed, verify login
#   frontend/scripts/e2e-stack.sh status   # docker compose ps for this project only
#   frontend/scripts/e2e-stack.sh logs     # follow backend logs for this project only
#   frontend/scripts/e2e-stack.sh down     # stop and remove ONLY this project's containers
#                                           # (add -v to also drop the mysql_data_e2e volume)
#
# Env overrides (defaults match docker-compose.e2e.yml):
#   E2E_COMPOSE_PROJECT   (default trocha-e2e)
#   E2E_API_PORT          (default 8001)  — host port mapped to the backend
#   E2E_MYSQL_PORT        (default 3307)  — host port mapped to MySQL
#   E2E_MAILHOG_PORT      (default 8026)  — host port mapped to the MailHog UI
#   E2E_COACH_EMAIL       (default entrenador@trochyruta.com — literal in e2e/anthropometry.spec.ts)
#   E2E_COACH_PASSWORD    (default Coach2026! — literal in e2e/anthropometry.spec.ts)
#
# Never reads, prints or copies the contents of .env / .env.* — MYSQL_*/JWT_*
# are interpolated by `docker compose` itself from the root .env at the host
# level; this script only ever curls published ports and greps container
# logs for the word "seed" (counts/status lines only, no secret values).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

PROJECT="${E2E_COMPOSE_PROJECT:-trocha-e2e}"
API_PORT="${E2E_API_PORT:-8001}"
MYSQL_PORT="${E2E_MYSQL_PORT:-3307}"
MAILHOG_PORT="${E2E_MAILHOG_PORT:-8026}"
COACH_EMAIL="${E2E_COACH_EMAIL:-entrenador@trochyruta.com}"
COACH_PASSWORD="${E2E_COACH_PASSWORD:-Coach2026!}"

COMPOSE=(docker compose -p "$PROJECT" -f docker-compose.yml -f docker-compose.e2e.yml)

# Guardrail: this script must never target the developer's "me" project.
if [ "$PROJECT" = "me" ]; then
  echo "e2e-stack: refusing to run against compose project \"me\" (the developer's real stack)." >&2
  exit 1
fi

log() { echo "[e2e-stack] $*"; }

cmd_up() {
  log "starting isolated stack (project=$PROJECT, api=:$API_PORT, mysql=:$MYSQL_PORT, mailhog=:$MAILHOG_PORT)"
  "${COMPOSE[@]}" up -d --build

  wait_health
  wait_seed
  verify_login

  log "stack is up and verified — leaving it running for the test run."
  log "next: E2E_APP_PORT=5175 E2E_API_BASE_URL=http://localhost:$API_PORT npx playwright test"
}

wait_health() {
  log "waiting for http://localhost:${API_PORT}/health ..."
  local attempt=0
  local max_attempts=60 # 60 * 2s = 120s — cold container + migrations
  until curl -fsS -o /dev/null "http://localhost:${API_PORT}/health"; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge "$max_attempts" ]; then
      echo "e2e-stack: backend never became healthy on :${API_PORT} after ${max_attempts} attempts." >&2
      "${COMPOSE[@]}" logs --tail=100 backend >&2 || true
      exit 1
    fi
    sleep 2
  done
  log "backend healthy on :${API_PORT}."
}

wait_seed() {
  log "waiting for the demo seed to finish (backend logs, no secrets)..."
  local attempt=0
  local max_attempts=30 # 30 * 2s = 60s
  until "${COMPOSE[@]}" logs backend 2>/dev/null | grep -qi "seed"; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge "$max_attempts" ]; then
      echo "e2e-stack: no seed-related log line appeared within ${max_attempts} attempts." >&2
      exit 1
    fi
    sleep 2
  done
  log "seed log lines found:"
  "${COMPOSE[@]}" logs backend 2>/dev/null | grep -i "seed"
}

verify_login() {
  log "verifying demo coach login (credentials already literal in frontend/e2e/anthropometry.spec.ts)..."
  local status
  status=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST "http://localhost:${API_PORT}/api/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"${COACH_EMAIL}\",\"password\":\"${COACH_PASSWORD}\"}")
  if [ "$status" != "200" ]; then
    echo "e2e-stack: demo coach login returned HTTP ${status}, expected 200." >&2
    exit 1
  fi
  log "demo coach login OK (HTTP 200)."
}

cmd_status() {
  "${COMPOSE[@]}" ps
}

cmd_logs() {
  "${COMPOSE[@]}" logs -f backend
}

cmd_down() {
  log "stopping isolated stack (project=$PROJECT) — this does not touch the \"me\" project."
  "${COMPOSE[@]}" down "$@"
}

case "${1:-up}" in
  up) cmd_up ;;
  status) cmd_status ;;
  logs) cmd_logs ;;
  down) shift; cmd_down "$@" ;;
  *)
    echo "Usage: $0 {up|status|logs|down [-v]}" >&2
    exit 1
    ;;
esac
