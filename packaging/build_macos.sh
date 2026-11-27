#!/usr/bin/env bash
# Builds the macOS app and disk image: dist/KAIRO.app and dist/KAIRO-<version>-macOS-<arch>.dmg
#   bash packaging/build_macos.sh
# Needs: macOS 11+, Python 3.12 with Tk (python.org installer or Homebrew python-tk), Homebrew portaudio.
#
# The app is signed "ad hoc" (no Apple Developer ID). macOS will warn the first time it opens; users
# right-click KAIRO.app > Open once. Proper signing + notarization needs a paid Apple Developer account.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PYTHON:-python3.12}

if [ ! -x .venv/bin/python ]; then
  echo "Creating .venv..."
  "$PY" -m venv .venv
fi
if ! brew list portaudio >/dev/null 2>&1; then
  echo "Installing portaudio (needed for the microphone)..."
  brew install portaudio
fi
.venv/bin/python -m pip install -q --upgrade pip
.venv/bin/python -m pip install -q -r requirements.txt -r requirements-build.txt

VERSION=$(.venv/bin/python -c "import version; print(version.__version__)")
ARCH=$(uname -m)
echo "== KAIRO $VERSION - macOS ($ARCH) build =="

echo "1/5 Running tests..."
.venv/bin/python -m unittest discover -s tests -t . 2>&1 | tail -3

echo "2/5 Drawing icons..."
.venv/bin/python packaging/make_icons.py >/dev/null

echo "3/5 Packaging the app (PyInstaller)..."
rm -rf build dist/KAIRO dist/KAIRO.app
.venv/bin/python -m PyInstaller packaging/kairo.spec --noconfirm --log-level WARN

echo "4/5 Self-test of the packaged app..."
TEST_HOME=$(mktemp -d)
if ! KAIRO_HOME="$TEST_HOME" dist/KAIRO.app/Contents/MacOS/KAIRO --selftest; then
    echo "Self-test FAILED:"; cat "$TEST_HOME/selftest.txt" 2>/dev/null || echo "(no selftest.txt was written)"
    exit 1
fi
cat "$TEST_HOME/selftest.txt"

echo "5/5 Signing (ad hoc) and making the disk image..."
codesign --force --deep --sign - dist/KAIRO.app
STAGE=$(mktemp -d)
cp -R dist/KAIRO.app "$STAGE/"
ln -s /Applications "$STAGE/Applications"
cat > "$STAGE/READ ME FIRST.txt" <<'EOF'
Installing KAIRO
1. Drag KAIRO into the Applications folder.
2. Open KAIRO from Applications. The first time, macOS says it can't check KAIRO for malicious software,
   because KAIRO isn't signed by a paid Apple developer account. To allow it (only needed once):
   - macOS 15 Sequoia or newer: click Done, open System Settings > Privacy & Security, scroll down,
     click "Open Anyway" next to KAIRO, and confirm with your password.
   - macOS 14 or older: RIGHT-click (or Control-click) KAIRO in Applications, choose Open, then Open again.
3. Allow microphone access when asked, so KAIRO can hear you.
A short setup guide then helps you choose its AI, test your microphone and pick a voice.
EOF
DMG="dist/KAIRO-$VERSION-macOS-$ARCH.dmg"
rm -f "$DMG"
hdiutil create -volname "KAIRO $VERSION" -srcfolder "$STAGE" -ov -format UDZO "$DMG" >/dev/null
(cd "$(dirname "$DMG")" && shasum -a 256 "$(basename "$DMG")") | tee "$DMG.sha256"
echo "Done: $DMG"
