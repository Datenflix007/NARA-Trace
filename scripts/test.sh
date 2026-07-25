#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"

python -m pip install -e "$BACKEND[test]"
python -m pytest "$BACKEND/tests"

if [[ -f "$FRONTEND/package.json" ]]; then
  (cd "$FRONTEND" && npm install && npm run test -- --run)
fi
