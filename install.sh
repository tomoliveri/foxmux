#!/bin/sh
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Installs the foxmux native messaging host for the current user.
# Usage: ./install.sh [--uninstall]

set -eu

HOST_NAME=foxmux
EXTENSION_ID=foxmux@foxmux
REPO_DIR=$(cd "$(dirname "$0")" && pwd)

case "$(uname -s)" in
  Darwin)
    MANIFEST_DIR="$HOME/Library/Application Support/Mozilla/NativeMessagingHosts"
    DATA_DIR="$HOME/Library/Application Support/foxmux"
    ;;
  Linux)
    MANIFEST_DIR="$HOME/.mozilla/native-messaging-hosts"
    DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/foxmux"
    ;;
  *)
    echo "foxmux: unsupported OS $(uname -s)" >&2
    exit 1
    ;;
esac

# macOS: run the tmux server from launchd, outside Firefox's process tree, so
# files written in a terminal tab aren't quarantined (see LAUNCH_AGENT in the host).
AGENT=foxmux.tmux-server
AGENT_PLIST="$HOME/Library/LaunchAgents/$AGENT.plist"
DOMAIN="gui/$(id -u)"

if [ "${1:-}" = "--uninstall" ]; then
  if [ "$(uname -s)" = Darwin ]; then
    launchctl bootout "$DOMAIN/$AGENT" 2>/dev/null || true
    rm -f "$AGENT_PLIST"
  fi
  rm -f "$MANIFEST_DIR/$HOST_NAME.json" "$DATA_DIR/foxmux_host.py"
  rmdir "$DATA_DIR" 2>/dev/null || true
  echo "foxmux native host removed."
  exit 0
fi

PYTHON=$(command -v python3 || true)
if [ -z "$PYTHON" ]; then
  echo "foxmux: python3 is required" >&2
  exit 1
fi
if ! command -v tmux >/dev/null 2>&1; then
  echo "foxmux: warning: tmux is not on PATH; install it before opening a terminal tab." >&2
fi

mkdir -p "$MANIFEST_DIR" "$DATA_DIR"

# Firefox starts the host with a minimal PATH, so pin the interpreter.
HOST="$DATA_DIR/foxmux_host.py"
{ echo "#!$PYTHON"; tail -n +2 "$REPO_DIR/native/foxmux_host.py"; } > "$HOST"
chmod 755 "$HOST"

cat > "$MANIFEST_DIR/$HOST_NAME.json" <<JSON
{
  "name": "$HOST_NAME",
  "description": "foxmux tmux bridge",
  "path": "$HOST",
  "type": "stdio",
  "allowed_extensions": ["$EXTENSION_ID"]
}
JSON

if [ "$(uname -s)" = Darwin ]; then
  mkdir -p "$(dirname "$AGENT_PLIST")"
  cat > "$AGENT_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$AGENT</string>
  <key>ProgramArguments</key>
  <array><string>$PYTHON</string><string>$HOST</string><string>--server</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ProcessType</key><string>Interactive</string>
</dict>
</plist>
PLIST
  # Written from a foxmux tab before this fix, the plist is quarantined and launchd refuses it.
  xattr -d com.apple.quarantine "$AGENT_PLIST" 2>/dev/null || true
  # Reloading a running agent would end every tmux session; changes apply at next login.
  launchctl print "$DOMAIN/$AGENT" >/dev/null 2>&1 || launchctl bootstrap "$DOMAIN" "$AGENT_PLIST"
fi

echo "foxmux native host installed:"
echo "  host:     $HOST"
echo "  manifest: $MANIFEST_DIR/$HOST_NAME.json"
if [ "$(uname -s)" = Darwin ]; then
  echo "  tmux server agent: $AGENT_PLIST"
fi
