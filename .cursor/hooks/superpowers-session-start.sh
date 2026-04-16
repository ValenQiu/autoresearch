#!/usr/bin/env bash
# Wrapper so sessionStart emits Cursor additional_context (see obra/superpowers hooks/session-start).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
export CURSOR_PLUGIN_ROOT="${CURSOR_PLUGIN_ROOT:-${ROOT}/third_party/superpowers}"
exec "${ROOT}/third_party/superpowers/hooks/session-start" "$@"
