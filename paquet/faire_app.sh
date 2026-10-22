#!/bin/bash
# Monte Root.app : une vraie app macOS qui lance la fenêtre de Root.
# Le lanceur appelle le venv et le code en place, donc tes mises à jour de
# code (git pull, édition) sont prises en compte sans reconstruire l'app.
set -e
ICI="$(cd "$(dirname "$0")" && pwd)"
RACINE="$(dirname "$ICI")"
VENV="${ROOT_VENV:-$HOME/.local/root-venv}"
APP="${1:-$ICI/Root.app}"

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Root</string>
  <key>CFBundleDisplayName</key><string>Root</string>
  <key>CFBundleIdentifier</key><string>com.vincent.root</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>Root</string>
  <key>CFBundleIconFile</key><string>Root</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>LSMinimumSystemVersion</key><string>11.0</string>
  <key>NSMicrophoneUsageDescription</key><string>Root écoute le micro quand tu le lui demandes.</string>
  <key>NSAppleEventsUsageDescription</key><string>Root ouvre des pages et des apps pour toi.</string>
</dict>
</plist>
PLIST

cp "$ICI/Root.icns" "$APP/Contents/Resources/Root.icns"

cat > "$APP/Contents/MacOS/Root" <<LANCEUR
#!/bin/bash
# Lanceur de Root : démarre la fenêtre avec le venv et le code en place.
cd "$RACINE"
exec "$VENV/bin/python" "$RACINE/fenetre.py" >> "\$HOME/.local/root-app.log" 2>&1
LANCEUR
chmod +x "$APP/Contents/MacOS/Root"

# rafraîchir l'icône dans le Finder/Dock
touch "$APP"
echo "Root.app monté : $APP"
