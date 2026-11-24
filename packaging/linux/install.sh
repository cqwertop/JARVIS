#!/usr/bin/env bash
# Installs JARVIS for the current user (no administrator password needed).
#   ./install.sh
# Program files: ~/.local/lib/jarvis   Your data (kept on update/uninstall): ~/.local/share/jarvis
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/.local/lib/jarvis"
BIN="$HOME/.local/bin"
APPS="$HOME/.local/share/applications"
ICONS="$HOME/.local/share/icons/hicolor/256x256/apps"

echo "Installing JARVIS..."
pkill -f "$DEST/JARVIS" 2>/dev/null && sleep 1 || true   # close a running copy before updating
rm -rf "$DEST"
mkdir -p "$DEST" "$BIN" "$APPS" "$ICONS"
cp -R "$HERE/app/." "$DEST/"
cp "$HERE/jarvis.png" "$ICONS/jarvis.png"
cp "$HERE/uninstall.sh" "$DEST/uninstall.sh"
ln -sf "$DEST/JARVIS" "$BIN/jarvis"
cat > "$APPS/jarvis.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=JARVIS
Comment=Your personal voice assistant
Exec=$DEST/JARVIS
Icon=jarvis
Terminal=false
Categories=Utility;
Actions=Settings;

[Desktop Action Settings]
Name=JARVIS Settings
Exec=$DEST/JARVIS --setup
EOF
update-desktop-database "$APPS" 2>/dev/null || true

missing=()
command -v pactl >/dev/null || command -v amixer >/dev/null || missing+=("pulseaudio-utils (volume control)")
command -v playerctl >/dev/null || missing+=("playerctl (music control)")
command -v ffplay >/dev/null || command -v mpg123 >/dev/null || command -v mpv >/dev/null || missing+=("ffmpeg (playing JARVIS's voice)")
command -v notify-send >/dev/null || missing+=("libnotify-bin (reminder pop-ups)")
echo
echo "JARVIS is installed. Open it from your applications menu, or type: jarvis"
if [ ${#missing[@]} -gt 0 ]; then
  echo
  echo "Optional extras that make JARVIS work better (install with your software centre or package manager):"
  printf '  - %s\n' "${missing[@]}"
  echo "  On Ubuntu/Debian: sudo apt install pulseaudio-utils playerctl ffmpeg libnotify-bin"
fi
