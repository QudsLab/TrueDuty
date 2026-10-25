#!/usr/bin/env bash
# Linux packages from the standalone build in app/dist/TrueDuty.
#   usage: linux.sh <version> <arch: x64|arm64> <out dir>
# Makes: .deb and .rpm (installers), .AppImage (single file, runs anywhere), portable .tar.gz (keeps data next to itself)
set -euo pipefail
V="$1"; A="$2"; OUT="$(realpath "$3")"; HERE="$(cd "$(dirname "$0")" && pwd)"; SRC="$(realpath "$HERE/../dist/TrueDuty")"
case "$A" in x64) DEB=amd64; RPM=x86_64; AI=x86_64;; arm64) DEB=arm64; RPM=aarch64; AI=aarch64;; *) echo "bad arch $A"; exit 1;; esac
ICON="$HERE/../assets/app-icon.png"; mkdir -p "$OUT"; W="$(mktemp -d)"
DESKTOP='[Desktop Entry]
Name=TrueDuty
Comment=Time and activity tracker
Exec=trueduty
Icon=trueduty
Terminal=false
Type=Application
Categories=Office;Utility;
StartupWMClass=TrueDuty'

# portable: folder + marker file, data stays in TrueDuty-data next to it
P="$W/TrueDuty-$V-linux-$A-portable"; cp -a "$SRC" "$P"; : > "$P/portable"
tar -C "$W" -czf "$OUT/TrueDuty-$V-linux-$A-portable.tar.gz" "$(basename "$P")"

# shared install tree: /opt/trueduty + launcher + menu entry + icon
R="$W/root"; mkdir -p "$R/opt" "$R/usr/bin" "$R/usr/share/applications" "$R/usr/share/icons/hicolor/512x512/apps" "$R/usr/share/doc/trueduty"
cp -a "$SRC" "$R/opt/trueduty"; ln -s /opt/trueduty/TrueDuty "$R/usr/bin/trueduty"
printf '%s\n' "$DESKTOP" > "$R/usr/share/applications/trueduty.desktop"; cp "$ICON" "$R/usr/share/icons/hicolor/512x512/apps/trueduty.png"
cp "$SRC/LICENSE" "$R/usr/share/doc/trueduty/copyright" 2>/dev/null || true

# .deb
D="$W/deb"; cp -a "$R" "$D"; mkdir -p "$D/DEBIAN"
SIZE=$(du -sk "$D/opt" | cut -f1)
cat > "$D/DEBIAN/control" <<C
Package: trueduty
Version: $V
Section: utils
Priority: optional
Architecture: $DEB
Installed-Size: $SIZE
Depends: libc6, libx11-6, libxss1
Recommends: xdotool
Maintainer: QudsLab <noreply@github.com>
Homepage: https://github.com/QudsLab/TrueDuty
Description: TrueDuty time and activity tracker
 Local-first time tracker that can connect to a TaskDash team.
C
dpkg-deb --root-owner-group --build "$D" "$OUT/trueduty_${V}_${DEB}.deb"

# .rpm (Fedora, RHEL, openSUSE)
if command -v rpmbuild >/dev/null; then
  T="$W/rpm"; mkdir -p "$T"/{BUILD,RPMS,SOURCES,SPECS,SRPMS,BUILDROOT}
  cat > "$T/SPECS/trueduty.spec" <<S
Name: trueduty
Version: $(echo "$V" | tr '-' '.')
Release: 1
Summary: TrueDuty time and activity tracker
License: MIT
URL: https://github.com/QudsLab/TrueDuty
AutoReqProv: no
%description
Local-first time tracker that can connect to a TaskDash team.
%install
cp -a $R/. %{buildroot}/
%files
/opt/trueduty
/usr/bin/trueduty
/usr/share/applications/trueduty.desktop
/usr/share/icons/hicolor/512x512/apps/trueduty.png
/usr/share/doc/trueduty
S
  rpmbuild --define "_topdir $T" --define "_build_id_links none" --target "$RPM" -bb "$T/SPECS/trueduty.spec"
  cp "$T"/RPMS/*/*.rpm "$OUT/trueduty-${V}.${RPM}.rpm"
fi

# .AppImage
AD="$W/TrueDuty.AppDir"; mkdir -p "$AD/usr"; cp -a "$SRC" "$AD/usr/bin"
printf '%s\n' "$DESKTOP" | sed 's/^Exec=.*/Exec=TrueDuty/' > "$AD/trueduty.desktop"; cp "$ICON" "$AD/trueduty.png"
printf '#!/bin/sh\nexec "$(dirname "$(readlink -f "$0")")/usr/bin/TrueDuty" "$@"\n' > "$AD/AppRun"; chmod +x "$AD/AppRun"
[ "${SKIP_APPIMAGE:-}" = 1 ] && { ls -la "$OUT"; exit 0; }
TOOL="$W/appimagetool"; curl -fsSL -o "$TOOL" "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-$AI.AppImage"; chmod +x "$TOOL"
ARCH=$AI APPIMAGE_EXTRACT_AND_RUN=1 "$TOOL" --no-appstream "$AD" "$OUT/TrueDuty-$V-linux-$A.AppImage"
ls -la "$OUT"
