#!/usr/bin/env bash
# Removes KAIRO (installed with install.sh). Asks before deleting your personal data.
set -uo pipefail
DEST="$HOME/.local/lib/kairo"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}/kairo"

pkill -f "$DEST/KAIRO" 2>/dev/null && sleep 1
read -r -p "Also delete your KAIRO data (memories, tasks, settings, saved API keys)? [y/N] " answer
if [[ "$answer" =~ ^[Yy] ]] && [ -x "$DEST/KAIRO" ]; then
  "$DEST/KAIRO" --remove-user-data && echo "Your KAIRO data was deleted."
else
  echo "Keeping your data in $DATA"
fi
rm -f "$HOME/.local/bin/kairo" "$HOME/.local/share/applications/kairo.desktop" \
      "$HOME/.local/share/icons/hicolor/256x256/apps/kairo.png" "$HOME/.config/autostart/kairo.desktop"
rm -rf "$DEST"
echo "KAIRO has been removed."
