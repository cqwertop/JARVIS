#!/usr/bin/env bash
# Builds the Linux packages:
#   dist/KAIRO-<version>-linux-<arch>.tar.gz   (any distribution: unpack, run ./install.sh - no root needed)
#   dist/kairo_<version>_<debarch>.deb         (Ubuntu, Debian, Mint, Pop!_OS...)
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
echo "== KAIRO $VERSION - Linux ($ARCH) build =="

echo "1/5 Running tests..."
.venv/bin/python -m unittest discover -s tests -t . 2>&1 | tail -3

echo "2/5 Drawing icons..."
.venv/bin/python packaging/make_icons.py >/dev/null

echo "3/5 Packaging the app (PyInstaller)..."
rm -rf build dist/KAIRO
.venv/bin/python -m PyInstaller packaging/kairo.spec --noconfirm --log-level WARN

echo "4/5 Self-test of the packaged app..."
TEST_HOME=$(mktemp -d)
if ! KAIRO_HOME="$TEST_HOME" dist/KAIRO/KAIRO --selftest; then
    echo "Self-test FAILED:"; cat "$TEST_HOME/selftest.txt" 2>/dev/null || echo "(no selftest.txt was written)"
    exit 1
fi
cat "$TEST_HOME/selftest.txt"

echo "5/5 Making the packages..."
# --- tarball with a per-user installer script
STAGE=$(mktemp -d)/KAIRO-$VERSION
mkdir -p "$STAGE"
cp -R dist/KAIRO "$STAGE/app"
cp packaging/assets/kairo-256.png "$STAGE/kairo.png"
cp packaging/linux/install.sh packaging/linux/uninstall.sh "$STAGE/"
cp packaging/linux/README.txt "$STAGE/"
chmod +x "$STAGE"/*.sh
TAR="dist/KAIRO-$VERSION-linux-$ARCH.tar.gz"
tar -C "$(dirname "$STAGE")" -czf "$TAR" "KAIRO-$VERSION"
(cd "$(dirname "$TAR")" && sha256sum "$(basename "$TAR")") | tee "$TAR.sha256"

# --- .deb (installs to /opt/kairo for all users)
PKG=$(mktemp -d)/kairo
mkdir -p "$PKG/DEBIAN" "$PKG/opt" "$PKG/usr/bin" "$PKG/usr/share/applications" "$PKG/usr/share/icons/hicolor/256x256/apps"
cp -R dist/KAIRO "$PKG/opt/kairo"
ln -s /opt/kairo/KAIRO "$PKG/usr/bin/kairo"
cp packaging/assets/kairo-256.png "$PKG/usr/share/icons/hicolor/256x256/apps/kairo.png"
sed "s|@EXEC@|/opt/kairo/KAIRO|" packaging/linux/kairo.desktop.in > "$PKG/usr/share/applications/kairo.desktop"
SIZE=$(du -sk "$PKG" | cut -f1)
cat > "$PKG/DEBIAN/control" <<EOF
Package: kairo
Version: $VERSION
Architecture: $DEBARCH
Maintainer: KAIRO Project <noreply@example.invalid>
Installed-Size: $SIZE
Depends: libportaudio2
Recommends: libnotify-bin, pulseaudio-utils | pipewire-pulse, playerctl, ffmpeg, espeak-ng, gnome-screenshot
Section: utils
Priority: optional
Description: KAIRO personal voice assistant
 Talk to your computer: ask questions, open apps, control music and volume,
 set reminders and keep notes. Works with online AI services or a local model.
EOF
DEB="dist/kairo_${VERSION}_${DEBARCH}.deb"
dpkg-deb --root-owner-group --build "$PKG" "$DEB" >/dev/null
(cd "$(dirname "$DEB")" && sha256sum "$(basename "$DEB")") | tee "$DEB.sha256"
echo "Done: $TAR and $DEB"
