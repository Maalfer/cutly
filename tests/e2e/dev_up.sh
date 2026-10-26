#!/usr/bin/env bash
# Levanta un servidor de desarrollo LOCAL (no toca producción) con datos de prueba reales.
# Uso: tests/e2e/dev_up.sh   → escribe tests/e2e/out/state.json   |   para pararlo: tests/e2e/dev_down.sh
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../.." && pwd); export PATH=$HOME/.local/bin:$PATH
D=${E2E_DATA:-$HOME/.cache/e2e-data}; PORT=${E2E_PORT:-8399}; mkdir -p "$D" "$REPO/tests/e2e/out"
export CUTLY_ENV=dev CUTLY_DATA_DIR=$D CUTLY_DATABASE_URL=sqlite:///$D/dev.db CUTLY_QUEUE_MODE=inline \
       CUTLY_SESSION_SECRET=dev-secret CUTLY_RATE_LIMIT_PER_MINUTE=100000 CUTLY_PASSWORD=testpass1234
cd "$REPO"
if [ ! -f "$D/dev.db" ]; then uv run cutly create-user test >/dev/null; fi
if ! curl -sf "http://127.0.0.1:$PORT/api/v1/health" >/dev/null; then
  nohup uv run uvicorn cutly.api.app:app --host 127.0.0.1 --port "$PORT" > "$D/server.log" 2>&1 &
  echo $! > "$D/server.pid"
  for i in $(seq 1 40); do curl -sf "http://127.0.0.1:$PORT/api/v1/health" >/dev/null && break; sleep 0.5; done
fi
uv run python tests/e2e/seed.py "http://127.0.0.1:$PORT" > tests/e2e/out/state.json
cat tests/e2e/out/state.json
