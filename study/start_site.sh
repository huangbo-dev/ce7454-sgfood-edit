#!/usr/bin/env bash
# Start the blinded team-annotation site (site_server.py) and expose it to the tailnet only (Tailscale Serve, no Funnel).
# Rootless: tailscaled runs in userspace-networking mode with its own state and socket.
#   ./start_site.sh          start, tailnet only (prints a login URL the first time)
#   ./start_site.sh public   publish via Funnel so team annotators off the tailnet can reach it (annotator codes required)
#   ./start_site.sh stop     stop server and tailscaled
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
TS_DIR="${SITE_TS_DIR:-$HOME/plateedit-v10/work/tailscale}"
ARCH=$(uname -m | sed "s/x86_64/amd64/;s/aarch64/arm64/")   # amd64 here, arm64 on the Spark
BIN=$(ls -d "$TS_DIR"/tailscale_*_"$ARCH" | sort -V | tail -1)
SOCK="$TS_DIR/tailscaled.sock"
TS="$BIN/tailscale --socket=$SOCK"
PORT="${SITE_PORT:-8766}"

if [ "${1:-}" = stop ]; then
  $TS serve --https=443 off 2>/dev/null
  pkill -f "site_server.py serve --port $PORT" ; pkill -f "tailscaled --tun=userspace-networking --socket=$SOCK"
  echo stopped; exit 0
fi

if ! curl -s -m 2 "http://127.0.0.1:$PORT/items.json" >/dev/null; then
  (cd "$HERE" && nohup "${SITE_PY:-python3}" -I "$HERE/site_server.py" serve --port $PORT >> "$HERE/server.log" 2>&1 &)
  sleep 1
fi
curl -s -m 2 "http://127.0.0.1:$PORT/items.json" >/dev/null && echo "rating server: http://127.0.0.1:$PORT"

if ! [ -S "$SOCK" ] || ! $TS status >/dev/null 2>&1 && ! $TS status 2>&1 | grep -q -i 'logged out\|NeedsLogin'; then
  nohup "$BIN/tailscaled" --tun=userspace-networking --socket="$SOCK" --statedir="$TS_DIR/state" \
    --port=41641 >> "$TS_DIR/tailscaled.log" 2>&1 &
  sleep 3
fi
if ! $TS status >/dev/null 2>&1; then
  echo "Log this machine into your tailnet (open the URL in a browser):"
  timeout 20 $TS up --hostname="${SITE_HOST:-sgfood-study}" --timeout=15s 2>&1 | grep -o 'https://login.tailscale.com[^ ]*' | head -1
  echo "Then run ./start_site.sh again."
  exit 0
fi
if [ "${1:-}" = public ]; then
  # Public internet via Tailscale Funnel. Every study route still needs an invitation code;
  # /admin stays tailnet-only. Funnel must be allowed in the tailnet policy (the CLI prints a link if not).
  $TS funnel --bg 443 "http://127.0.0.1:$PORT" || exit 1
  echo "PUBLIC URL (invitation code required):"
else
  $TS funnel --https=443 off >/dev/null 2>&1
  $TS serve --bg --https=443 "http://127.0.0.1:$PORT" >/dev/null
  echo "tailnet URL:"
fi
$TS serve status 2>/dev/null | grep -o 'https://[^ ]*' | head -1
