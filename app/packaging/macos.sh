#!/usr/bin/env bash
# macOS packages from app/dist/TrueDuty.app.   usage: macos.sh <version> <arch: arm64|x64> <out dir>
# Makes: .dmg (drag to Applications), .pkg (installer), portable .zip
# Signing: MAC_IDENTITY (Developer ID Application) signs the app and dmg, MAC_INSTALLER_IDENTITY (Developer ID Installer)
# signs the pkg, APPLE_ID + APPLE_TEAM_ID + APPLE_APP_PASSWORD notarize and staple. Without them the app is ad hoc signed.
set -euo pipefail
V="$1"; A="$2"; OUT="$(realpath "$3")"; HERE="$(cd "$(dirname "$0")" && pwd)"; APP="$HERE/../dist/TrueDuty.app"; mkdir -p "$OUT"
ID="${MAC_IDENTITY:--}"
ENT="$HERE/entitlements.plist"
if [ "$ID" = "-" ]; then codesign --force --deep --sign - "$APP"
else codesign --force --deep --options runtime --timestamp --entitlements "$ENT" --sign "$ID" "$APP"; fi
codesign --verify --deep --strict "$APP"
notarize() { if [ "$ID" != "-" ] && [ -n "${APPLE_ID:-}" ]; then xcrun notarytool submit "$1" --apple-id "$APPLE_ID" --team-id "$APPLE_TEAM_ID" --password "$APPLE_APP_PASSWORD" --wait; xcrun stapler staple "$1" || true; fi; }
# notarize the app itself first so the portable zip is trusted offline too
if [ "$ID" != "-" ] && [ -n "${APPLE_ID:-}" ]; then ditto -c -k --keepParent "$APP" /tmp/n.zip; notarize /tmp/n.zip; xcrun stapler staple "$APP"; fi
W="$(mktemp -d)"
# portable
mkdir -p "$W/p"; cp -R "$APP" "$W/p/"; : > "$W/p/portable"
(cd "$W/p" && ditto -c -k --sequesterRsrc . "$OUT/TrueDuty-$V-macos-$A-portable.zip")
# dmg
mkdir -p "$W/dmg"; cp -R "$APP" "$W/dmg/"; ln -s /Applications "$W/dmg/Applications"
hdiutil create -volname "TrueDuty $V" -srcfolder "$W/dmg" -ov -format UDZO "$OUT/TrueDuty-$V-macos-$A.dmg"
[ "$ID" != "-" ] && codesign --force --timestamp --sign "$ID" "$OUT/TrueDuty-$V-macos-$A.dmg"
notarize "$OUT/TrueDuty-$V-macos-$A.dmg"
# pkg
mkdir -p "$W/pkg"; cp -R "$APP" "$W/pkg/"
PK=(pkgbuild --root "$W/pkg" --install-location /Applications --identifier org.qudslab.trueduty --version "$V")
[ -n "${MAC_INSTALLER_IDENTITY:-}" ] && PK+=(--sign "$MAC_INSTALLER_IDENTITY" --timestamp)
"${PK[@]}" "$OUT/TrueDuty-$V-macos-$A.pkg"
[ -n "${MAC_INSTALLER_IDENTITY:-}" ] && notarize "$OUT/TrueDuty-$V-macos-$A.pkg"
ls -la "$OUT"
