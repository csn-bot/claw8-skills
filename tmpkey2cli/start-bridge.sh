#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ -f .env ]]; then
  set -a
  # shellcheck source=/dev/null
  source .env
  set +a
fi

if [[ -z "${DAYONE_BRIDGE_TOKEN:-}" ]]; then
  echo "error: DAYONE_BRIDGE_TOKEN is not set (add it to .env — see .env.example)" >&2
  exit 1
fi

exec node "$SCRIPT_DIR/dayone-cli-bridge.js"
