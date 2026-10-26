#!/usr/bin/env bash
D=${E2E_DATA:-$HOME/.cache/e2e-data}; [ -f "$D/server.pid" ] && kill "$(cat "$D/server.pid")" 2>/dev/null; rm -f "$D/server.pid"; echo parado
