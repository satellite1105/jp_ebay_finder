#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

# Override UV_BIN on hosts where uv is installed elsewhere.
UV_BIN="${UV_BIN:-/Users/gz_a10051/.local/bin/uv}"
EXPORT_DIR="${EXPORT_DIR:-${PROJECT_DIR}/output/daily}"

cd -- "${PROJECT_DIR}"
exec "${UV_BIN}" run finder daily --stale-only --export-dir "${EXPORT_DIR}" "$@"
