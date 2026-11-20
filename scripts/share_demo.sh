#!/usr/bin/env bash
# Share a temporary public link to a locally running VEIN SEARCH.
#
#   ./scripts/share_demo.sh
#
# Starts the app if it is not already running on $PORT, then opens a
# Cloudflare quick tunnel and prints a https://<random>.trycloudflare.com URL.
# The URL lives only while this script runs, and the machine must stay awake.
set -euo pipefail

PORT="${PORT:-8000}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
BIN="${CLOUDFLARED_BIN:-$ROOT/.tools/cloudflared}"
SERVER_PID=""

cleanup() {
  if [ -n "$SERVER_PID" ]; then
    echo "→ stopping app started by this script"
    kill "$SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

if curl -sf -m 3 "http://localhost:$PORT/api/health" >/dev/null 2>&1; then
  echo "→ app already running on :$PORT"
else
  echo "→ starting VEIN SEARCH on :$PORT (first run loads the CLIP model, ~5-20 s)"
  python3 -m uvicorn backend.main:app --port "$PORT" &
  SERVER_PID=$!
  for _ in $(seq 1 90); do
    sleep 1
    curl -sf -m 2 "http://localhost:$PORT/api/health" >/dev/null 2>&1 && break
  done
  curl -sf -m 3 "http://localhost:$PORT/api/health" >/dev/null 2>&1 \
    || { echo "✗ app failed to start — check the log above"; exit 1; }
  echo "→ app healthy"
fi

case "$(uname -s)-$(uname -m)" in
  Linux-x86_64)  ASSET=cloudflared-linux-amd64 ;;
  Linux-aarch64) ASSET=cloudflared-linux-arm64 ;;
  Darwin-*)      ASSET=cloudflared-darwin-amd64 ;;
  *)             ASSET=cloudflared-linux-amd64 ;;
esac

if [ ! -x "$BIN" ]; then
  echo "→ downloading cloudflared ($ASSET) once, ~40 MB"
  mkdir -p "$(dirname "$BIN")"
  curl -fsSL --retry 3 --max-time 900 -o "$BIN" \
    "https://github.com/cloudflare/cloudflared/releases/latest/download/$ASSET"
  chmod +x "$BIN"
fi

echo "→ opening public tunnel; the link appears below as https://<name>.trycloudflare.com"
echo "→ Ctrl+C closes the public link"
"$BIN" tunnel --url "http://localhost:$PORT" --no-autoupdate
