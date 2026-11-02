#!/bin/sh
# build.sh: VM Router (Mantra).app, swiftc straight, no Xcode, arm64, signed "Mantra Apps" (mac-app-signing.md),
# installed in /Applications, then the running copy is quit through its OFF (AX) and the new one opened
# (swift-apps.md, relaunch). OFF quits only the window: the router (vm-router.py) keeps serving its sessions.
#   ./build.sh            build, install, relaunch          ./build.sh --no-run   build and install only
set -e
cd "$(dirname "$0")"
V=$(sed -n 's/^let VERSION = \([0-9]*\)/\1/p' app/App.swift)
NAME="VM Router (Mantra)"; BID="community.auroville.vmrouter"
APP="build/$NAME.app"
rm -rf "$APP"; mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
swiftc -O -swift-version 5 -parse-as-library -target arm64-apple-macosx14.0 -o "$APP/Contents/MacOS/VMRouter" app/*.swift
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
<key>CFBundleIdentifier</key><string>$BID</string>
<key>CFBundleExecutable</key><string>VMRouter</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>$V</string>
<key>CFBundleVersion</key><string>$V</string>
<key>LSMinimumSystemVersion</key><string>14.0</string>
<key>NSHighResolutionCapable</key><true/>
<key>NSAppTransportSecurity</key><dict><key>NSAllowsLocalNetworking</key><true/></dict>
</dict></plist>
PL
codesign --force -s "Mantra Apps" "$APP"
RELAUNCH="$HOME/Developer/MANTRA_SOUND_RECORDER/tools/relaunch.swift"
if [ "$1" = "--no-run" ]; then
  rm -rf "/Applications/$NAME.app"; cp -R "$APP" /Applications/
  echo "built and installed $NAME v$V (not opened)"
else
  # relaunch.swift quits the running copy through its OFF, then opens the path it is given
  rm -rf "/Applications/$NAME.app"; cp -R "$APP" /Applications/
  swift "$RELAUNCH" "$BID" "/Applications/$NAME.app" || true
  echo "built $NAME v$V, installed in /Applications"
fi
