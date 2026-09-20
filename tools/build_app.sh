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
# The source art is a floral M on a white ground. Composited straight onto a
# plate it shows as a white square inside the rounded corners, so the ground
# is keyed out and only the florals land on the plate.
"$PYTHON" - "$LOGO" "$BUILD/icon" <<'PY'
import sys, pathlib
from PIL import Image, ImageDraw, ImageFilter
import numpy as np

logo, out_dir = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
src = Image.open(logo).convert("RGBA")

a = np.asarray(src).astype(np.float32)
lum = a[..., :3].min(axis=-1)
a[..., 3] = np.clip((246.0 - lum) / 14.0, 0.0, 1.0) * 255.0   # soft key
art = Image.fromarray(a.astype(np.uint8), "RGBA")
art = art.crop(art.getchannel("A").getbbox())

CANVAS, PLATE, RADIUS, PAD = 1024, 824, 185, 74   # Apple's Big Sur grid
inner = PLATE - PAD * 2
s = min(inner / art.width, inner / art.height)
art = art.resize((round(art.width * s), round(art.height * s)), Image.LANCZOS)

icon = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
box = ((CANVAS - PLATE) // 2,) * 2 + ((CANVAS + PLATE) // 2,) * 2

shadow = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
ImageDraw.Draw(shadow).rounded_rectangle(
    (box[0], box[1] + 10, box[2], box[3] + 14), radius=RADIUS,
    fill=(78, 68, 64, 66))
icon.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(15)))

plate = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
ImageDraw.Draw(plate).rounded_rectangle(box, radius=RADIUS,
                                        fill=(254, 253, 251, 255))
icon.alpha_composite(plate)
icon.alpha_composite(art, ((CANVAS - art.width) // 2,
                           (CANVAS - art.height) // 2))

iconset = out_dir / "Mnemonica.iconset"
iconset.mkdir(parents=True, exist_ok=True)
for f in iconset.glob("*.png"):
    f.unlink()
for size in (16, 32, 128, 256, 512):
    icon.resize((size, size), Image.LANCZOS).save(iconset / f"icon_{size}x{size}.png")
    icon.resize((size * 2, size * 2), Image.LANCZOS).save(
        iconset / f"icon_{size}x{size}@2x.png")
print("  icon: 10 sizes")
PY

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
