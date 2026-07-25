#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$ROOT/backend${PYTHONPATH:+:$PYTHONPATH}"

python -m naratrace "$@"
