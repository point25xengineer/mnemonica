#!/bin/bash
# Build Mnemonica.app.
#
#   ./tools/build_app.sh [--install]
#
# The bundle is a build artifact, not source: it hardcodes this checkout's
# path and this machine's interpreter, so it is gitignored and regenerated
# rather than committed. Everything it needs ships with macOS — sips and
# iconutil for the icon, bash for the launcher — so there is nothing to
# install first.
#
# --install also copies it to ~/Applications, which Spotlight and Launchpad
# index without needing an admin prompt.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${MNEMONICA_PYTHON:-/Users/evancanty/vn-shared/.venv/bin/python}"
LOGO="${MNEMONICA_LOGO:-$REPO/assets/logo.png}"
BUILD="$REPO/build"
APP="$BUILD/Mnemonica.app"

[ -x "$PYTHON" ] || { echo "no interpreter at $PYTHON (set MNEMONICA_PYTHON)"; exit 1; }
[ -f "$LOGO" ]   || { echo "no logo at $LOGO (set MNEMONICA_LOGO)"; exit 1; }

echo "building $APP"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources" "$BUILD/icon"

# ---- icon -----------------------------------------------------------------
"$PYTHON" "$REPO/tools/make_icon.py" "$LOGO" "$BUILD/icon"

iconutil -c icns "$BUILD/icon/Mnemonica.iconset" -o "$APP/Contents/Resources/Mnemonica.icns"

# ---- Info.plist -----------------------------------------------------------
cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key>              <string>Mnemonica</string>
  <key>CFBundleDisplayName</key>       <string>Mnemonica</string>
  <key>CFBundleIdentifier</key>        <string>io.mnemonica.app</string>
  <key>CFBundleVersion</key>           <string>1.0</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundleExecutable</key>        <string>Mnemonica</string>
  <key>CFBundleIconFile</key>          <string>Mnemonica</string>
  <key>CFBundlePackageType</key>       <string>APPL</string>
  <key>LSMinimumSystemVersion</key>    <string>13.0</string>
  <key>NSHighResolutionCapable</key>   <true/>
  <key>NSMicrophoneUsageDescription</key>
  <string>Mnemonica records the consultation on this device. The audio never leaves it.</string>
</dict>
</plist>
PLIST

# ---- launcher -------------------------------------------------------------
sed -e "s|__REPO__|$REPO|g" -e "s|__PYTHON__|$PYTHON|g" \
    "$REPO/tools/launcher.sh" > "$APP/Contents/MacOS/Mnemonica"
chmod +x "$APP/Contents/MacOS/Mnemonica"
bash -n "$APP/Contents/MacOS/Mnemonica"

plutil -lint "$APP/Contents/Info.plist" >/dev/null
touch "$APP"                      # nudge Finder to pick up the new icon
echo "  built $APP"

if [ "${1:-}" = "--install" ]; then
  mkdir -p "$HOME/Applications"
  rm -rf "$HOME/Applications/Mnemonica.app"
  cp -R "$APP" "$HOME/Applications/"
  touch "$HOME/Applications/Mnemonica.app"
  echo "  installed to ~/Applications/Mnemonica.app"
fi
