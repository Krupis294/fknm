#!/bin/sh
# Installs fknm for the current user, running from this checkout:
#   ~/.local/bin/fknm, fknm-rofi                     (symlinks)
#   ~/.local/share/applications/<app-id>.desktop     (launcher entry)
set -eu

root=$(cd "$(dirname "$0")" && pwd)
bin_dir="$HOME/.local/bin"
apps_dir="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
desktop="$apps_dir/io.github.krupis294.Fknm.desktop"

mkdir -p "$bin_dir" "$apps_dir"
for name in fknm fknm-rofi; do
    ln -sf "$root/bin/$name" "$bin_dir/$name"
done
sed "s|@EXEC@|$root/bin/fknm|" "$root/data/io.github.krupis294.Fknm.desktop.in" > "$desktop"
command -v update-desktop-database >/dev/null && update-desktop-database "$apps_dir" || true

echo "Nainstalováno: $bin_dir/fknm, $bin_dir/fknm-rofi, $desktop"
