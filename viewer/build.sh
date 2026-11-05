#!/bin/sh
# build.sh: Chromium Virtual Machine (Mantra).app, swiftc straight, no Xcode, arm64 (the-machine.md), signed
# "Mantra Apps" (mac-app-signing.md), installed in /Applications. The version is the one number in app/App.swift.
set -e
cd "$(dirname "$0")"
V=$(sed -n 's/^let VERSION = \([0-9]*\)/\1/p' app/App.swift)
NAME="Chromium Virtual Machine (Mantra)"
APP="build/$NAME.app"
rm -rf "$APP"; mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
swiftc -O -swift-version 5 -parse-as-library -target arm64-apple-macosx14.0 -o "$APP/Contents/MacOS/ChromiumVM" app/*.swift
(cd icon && swift make_icon.swift "$V" >/dev/null)
I=build/AppIcon.iconset; rm -rf $I; mkdir -p $I
for s in 16 32 128 256 512; do
  sips -z $s $s icon/icon_1024.png --out $I/icon_${s}x${s}.png >/dev/null
  sips -z $((s*2)) $((s*2)) icon/icon_1024.png --out $I/icon_${s}x${s}@2x.png >/dev/null
done
iconutil -c icns $I -o "$APP/Contents/Resources/AppIcon.icns"
cat > "$APP/Contents/Info.plist" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleName</key><string>$NAME</string>
<key>CFBundleDisplayName</key><string>$NAME</string>
<key>CFBundleIconFile</key><string>AppIcon</string>
<key>CFBundleIdentifier</key><string>community.auroville.chromiumvm</string>
<key>CFBundleExecutable</key><string>ChromiumVM</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>$V</string>
<key>CFBundleVersion</key><string>$V</string>
<key>LSMinimumSystemVersion</key><string>14.0</string>
<key>NSHighResolutionCapable</key><true/>
<key>NSAppTransportSecurity</key><dict><key>NSAllowsArbitraryLoads</key><true/></dict>
</dict></plist>
PL
codesign --force -s "${SIGN:-Mantra Apps}" "$APP"   # GitHub: SIGN=- (ad hoc)
[ -n "$NO_INSTALL" ] && { echo "built $APP (v$V)"; exit 0; }
# relaunch-after-build: quit the running copy, install, open the new one
osascript -e "tell application \"$NAME\" to quit" >/dev/null 2>&1 || true
sleep 1
rm -rf "/Applications/$NAME.app"; cp -R "$APP" /Applications/
echo "built $APP (v$V) and installed it in /Applications"
open -g "/Applications/$NAME.app"   # the new one, in the background (never takes his focus)
