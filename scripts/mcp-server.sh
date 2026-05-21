#!/usr/bin/env bash
# Launch the Intake Genius MCP server.
#
# Usage:
#   ./scripts/mcp-server.sh            # stdio (for Claude Desktop)
#   ./scripts/mcp-server.sh --sse      # SSE transport on port 8001

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PYTHON="$PROJECT_DIR/.venv/bin/python"

if [ ! -f "$PYTHON" ]; then
  echo "Error: virtualenv not found at $PROJECT_DIR/.venv" >&2
  echo "Run: python -m venv .venv && .venv/bin/pip install -e '.[dev]'" >&2
  exit 1
fi

cd "$PROJECT_DIR"

if [ "${1:-}" = "--sse" ]; then
  PORT="${2:-8001}"
  echo "Starting Intake Genius MCP server (SSE) on port $PORT…"
  exec "$PROJECT_DIR/.venv/bin/fastmcp" run src/mcp_server.py --transport sse --port "$PORT"
else
  exec "$PYTHON" -m src.mcp_server
fi
