#!/usr/bin/env bash
# Installs KAIRO for the current user (no administrator password needed).
#   ./install.sh
# Program files: ~/.local/lib/kairo   Your data (kept on update/uninstall): ~/.local/share/kairo
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/.local/lib/kairo"
BIN="$HOME/.local/bin"
APPS="$HOME/.local/share/applications"
ICONS="$HOME/.local/share/icons/hicolor/256x256/apps"

echo "Installing KAIRO..."
pkill -f "$DEST/KAIRO" 2>/dev/null && sleep 1 || true   # close a running copy before updating
rm -rf "$DEST"
mkdir -p "$DEST" "$BIN" "$APPS" "$ICONS"
cp -R "$HERE/app/." "$DEST/"
cp "$HERE/kairo.png" "$ICONS/kairo.png"
cp "$HERE/uninstall.sh" "$DEST/uninstall.sh"
ln -sf "$DEST/KAIRO" "$BIN/kairo"
cat > "$APPS/kairo.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=KAIRO
Comment=Your personal voice assistant
Exec=$DEST/KAIRO
Icon=kairo
Terminal=false
Categories=Utility;
Actions=Settings;

[Desktop Action Settings]
Name=KAIRO Settings
Exec=$DEST/KAIRO --setup
EOF
update-desktop-database "$APPS" 2>/dev/null || true

missing=()
command -v pactl >/dev/null || command -v amixer >/dev/null || missing+=("pulseaudio-utils (volume control)")
command -v playerctl >/dev/null || missing+=("playerctl (music control)")
command -v ffplay >/dev/null || command -v mpg123 >/dev/null || command -v mpv >/dev/null || missing+=("ffmpeg (playing KAIRO's voice)")
command -v notify-send >/dev/null || missing+=("libnotify-bin (reminder pop-ups)")
echo
echo "KAIRO is installed. Open it from your applications menu, or type: kairo"
if [ ${#missing[@]} -gt 0 ]; then
  echo
  echo "Optional extras that make KAIRO work better (install with your software centre or package manager):"
  printf '  - %s\n' "${missing[@]}"
  echo "  On Ubuntu/Debian: sudo apt install pulseaudio-utils playerctl ffmpeg libnotify-bin"
fi
