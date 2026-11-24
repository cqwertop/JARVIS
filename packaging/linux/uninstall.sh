#!/usr/bin/env bash
# Removes JARVIS (installed with install.sh). Asks before deleting your personal data.
set -uo pipefail
DEST="$HOME/.local/lib/jarvis"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}/jarvis"

pkill -f "$DEST/JARVIS" 2>/dev/null && sleep 1
read -r -p "Also delete your JARVIS data (memories, tasks, settings, saved API keys)? [y/N] " answer
if [[ "$answer" =~ ^[Yy] ]] && [ -x "$DEST/JARVIS" ]; then
  "$DEST/JARVIS" --remove-user-data && echo "Your JARVIS data was deleted."
else
  echo "Keeping your data in $DATA"
fi
rm -f "$HOME/.local/bin/jarvis" "$HOME/.local/share/applications/jarvis.desktop" \
      "$HOME/.local/share/icons/hicolor/256x256/apps/jarvis.png" "$HOME/.config/autostart/jarvis.desktop"
rm -rf "$DEST"
echo "JARVIS has been removed."
