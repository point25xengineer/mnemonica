#!/bin/bash
# Mnemonica launcher.
#
# Double-clicking the icon should behave like an app: no terminal, no URL bar,
# no "now open this address" step, and quitting should actually stop the
# server rather than leaving a port bound until the next reboot.
#
# So: start the server on a free port, wait until it genuinely answers, open a
# chromeless window pointed at it, and block on that window. When it closes,
# the trap takes the server down with it.

set -u

REPO="__REPO__"
PYTHON="__PYTHON__"
SUPPORT="$HOME/Library/Application Support/Mnemonica"
LOG="$SUPPORT/mnemonica.log"
PROFILE="$SUPPORT/browser"          # persisted, so the microphone grant sticks

mkdir -p "$SUPPORT" "$PROFILE"
exec >>"$LOG" 2>&1
echo "--- $(date '+%Y-%m-%d %H:%M:%S') launch ---"

die() {
  # A GUI app has no stderr anyone will read, so failures have to be said out
  # loud or they look like the icon simply doing nothing.
  osascript -e "display dialog \"$1\" with title \"Mnemonica\" buttons {\"OK\"} with icon caution" >/dev/null 2>&1
  echo "FATAL: $1"
  exit 1
}

[ -d "$REPO" ]     || die "Mnemonica cannot find its project folder at $REPO."
[ -x "$PYTHON" ]   || die "Mnemonica cannot find its Python environment. Expected $PYTHON."

# A free port, so a stale process from a previous run cannot block startup.
PORT="$("$PYTHON" - <<'PY'
import socket
s = socket.socket(); s.bind(("127.0.0.1", 0))
print(s.getsockname()[1]); s.close()
PY
)"
[ -n "$PORT" ] || die "Mnemonica could not reserve a local port."
URL="http://127.0.0.1:$PORT/"

cd "$REPO" || die "Cannot enter $REPO."
"$PYTHON" -m mnemonica.ui.app --port "$PORT" &
SERVER=$!

cleanup() {
  if kill -0 "$SERVER" 2>/dev/null; then
    kill "$SERVER" 2>/dev/null
    # Give it a moment to shred anything mid-write before insisting.
    for _ in 1 2 3 4 5 6 7 8 9 10; do
      kill -0 "$SERVER" 2>/dev/null || break
      sleep 0.2
    done
    kill -9 "$SERVER" 2>/dev/null
  fi
  echo "--- stopped ---"
}
trap cleanup EXIT INT TERM

# Wait for a real answer, not just a bound socket: opening the window early
# shows a connection error, which reads as a broken app.
READY=""
for _ in $(seq 1 100); do
  if curl -fsS -o /dev/null --max-time 1 "$URL"; then READY=1; break; fi
  kill -0 "$SERVER" 2>/dev/null || die "Mnemonica's server stopped while starting. See $LOG."
  sleep 0.2
done
[ -n "$READY" ] || die "Mnemonica's server did not start in time. See $LOG."

CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
if [ -x "$CHROME" ]; then
  # --app removes the tab strip and address bar; --kiosk removes the window
  # frame and the menu bar too, so the screen is only ever the consultation.
  # (--start-fullscreen was tried first and only maximises under the menu
  # bar; macOS native fullscreen also animates into its own Space, which is
  # a transition rather than the absence of one.)
  #
  # There is no close button in kiosk, so Cmd-Q is the way out — it drops the
  # renderers, which is the same signal a closed window gives.
  #
  # The persisted profile is what makes the microphone a one-time question.
  "$CHROME" --app="$URL" \
            --user-data-dir="$PROFILE" \
            --no-first-run --no-default-browser-check \
            --kiosk &
  BROWSER=$!

  # Waiting on that process does NOT work: on macOS Chrome keeps running with
  # zero windows, so the launcher would block forever and the server would
  # outlive the app. Renderer processes are the honest signal — one per open
  # window, none when the last one closes, and scoped to our own profile so
  # the user's separate Chrome is never counted.
  renderers() {
    ps -Ao command | grep -F -- "--user-data-dir=$PROFILE" \
                   | grep -c -- "--type=renderer"
  }

  for _ in $(seq 1 75); do        # give the first window time to appear
    [ "$(renderers)" -gt 0 ] && break
    sleep 0.2
  done

  # Debounced: a navigation can momentarily drop every renderer, and treating
  # that as a quit would close the app mid-consultation.
  EMPTY=0
  while :; do
    if [ "$(renderers)" -eq 0 ]; then
      EMPTY=$((EMPTY + 1))
      [ "$EMPTY" -ge 4 ] && break
    else
      EMPTY=0
    fi
    sleep 0.4
  done

  echo "window closed; shutting down"
  kill "$BROWSER" 2>/dev/null
  # Chrome lingers windowless; take our instance with us so the next launch
  # starts clean rather than attaching to a stale one.
  pkill -f -- "--user-data-dir=$PROFILE" 2>/dev/null
else
  # No Chrome: the default browser works, but it cannot tell us when the user
  # is finished, so the app stays alive until it is quit from the Dock.
  open "$URL"
  osascript -e 'display dialog "Mnemonica is running in your browser.\n\nClick Quit when you are finished." with title "Mnemonica" buttons {"Quit"} default button "Quit"' >/dev/null 2>&1
fi
