#!/usr/bin/env bash
# Builds the Linux packages:
#   dist/JARVIS-<version>-linux-<arch>.tar.gz   (any distribution: unpack, run ./install.sh - no root needed)
#   dist/jarvis_<version>_<debarch>.deb         (Ubuntu, Debian, Mint, Pop!_OS...)
#   bash packaging/build_linux.sh
# Needs: Python 3.12 with Tk (python3.12-venv, python3-tk), portaudio19-dev, dpkg-deb, and a display
# for the self-test (on a server use: xvfb-run bash packaging/build_linux.sh).
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PYTHON:-python3.12}

[ -x .venv/bin/python ] || "$PY" -m venv .venv
.venv/bin/python -m pip install -q --upgrade pip
.venv/bin/python -m pip install -q -r requirements.txt -r requirements-build.txt

VERSION=$(.venv/bin/python -c "import version; print(version.__version__)")
ARCH=$(uname -m)
DEBARCH=$(dpkg --print-architecture 2>/dev/null || echo amd64)
echo "== JARVIS $VERSION - Linux ($ARCH) build =="

echo "1/5 Running tests..."
.venv/bin/python -m unittest discover -s tests -t . 2>&1 | tail -3

echo "2/5 Drawing icons..."
.venv/bin/python packaging/make_icons.py >/dev/null

echo "3/5 Packaging the app (PyInstaller)..."
rm -rf build dist/JARVIS
.venv/bin/python -m PyInstaller packaging/jarvis.spec --noconfirm --log-level WARN

echo "4/5 Self-test of the packaged app..."
TEST_HOME=$(mktemp -d)
JARVIS_HOME="$TEST_HOME" dist/JARVIS/JARVIS --selftest
cat "$TEST_HOME/selftest.txt"

echo "5/5 Making the packages..."
# --- tarball with a per-user installer script
STAGE=$(mktemp -d)/JARVIS-$VERSION
mkdir -p "$STAGE"
cp -R dist/JARVIS "$STAGE/app"
cp packaging/assets/jarvis-256.png "$STAGE/jarvis.png"
cp packaging/linux/install.sh packaging/linux/uninstall.sh "$STAGE/"
cp packaging/linux/README.txt "$STAGE/"
chmod +x "$STAGE"/*.sh
TAR="dist/JARVIS-$VERSION-linux-$ARCH.tar.gz"
tar -C "$(dirname "$STAGE")" -czf "$TAR" "JARVIS-$VERSION"
sha256sum "$TAR" | tee "$TAR.sha256"

# --- .deb (installs to /opt/jarvis for all users)
PKG=$(mktemp -d)/jarvis
mkdir -p "$PKG/DEBIAN" "$PKG/opt" "$PKG/usr/bin" "$PKG/usr/share/applications" "$PKG/usr/share/icons/hicolor/256x256/apps"
cp -R dist/JARVIS "$PKG/opt/jarvis"
ln -s /opt/jarvis/JARVIS "$PKG/usr/bin/jarvis"
cp packaging/assets/jarvis-256.png "$PKG/usr/share/icons/hicolor/256x256/apps/jarvis.png"
sed "s|@EXEC@|/opt/jarvis/JARVIS|" packaging/linux/jarvis.desktop.in > "$PKG/usr/share/applications/jarvis.desktop"
SIZE=$(du -sk "$PKG" | cut -f1)
cat > "$PKG/DEBIAN/control" <<EOF
Package: jarvis
Version: $VERSION
Architecture: $DEBARCH
Maintainer: JARVIS Project <noreply@example.invalid>
Installed-Size: $SIZE
Depends: libportaudio2
Recommends: libnotify-bin, pulseaudio-utils | pipewire-pulse, playerctl, ffmpeg, espeak-ng, gnome-screenshot
Section: utils
Priority: optional
Description: JARVIS personal voice assistant
 Talk to your computer: ask questions, open apps, control music and volume,
 set reminders and keep notes. Works with online AI services or a local model.
EOF
DEB="dist/jarvis_${VERSION}_${DEBARCH}.deb"
dpkg-deb --root-owner-group --build "$PKG" "$DEB" >/dev/null
sha256sum "$DEB" | tee "$DEB.sha256"
echo "Done: $TAR and $DEB"
