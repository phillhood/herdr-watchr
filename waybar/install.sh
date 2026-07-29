#!/usr/bin/env bash
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
src="$here/herdr-watchr"
dest_dir="${HERDR_WATCHR_PREFIX:-$HOME/.local/bin}"
dest="$dest_dir/herdr-watchr"
mode=symlink

for arg in "$@"; do
  case "$arg" in
    --copy) mode=copy ;;
    -h|--help) printf 'usage: install.sh [--copy]\n'; exit 0 ;;
    *) printf 'install.sh: unknown option %s\n' "$arg" >&2; exit 2 ;;
  esac
done

mkdir -p "$dest_dir"
if [ "$mode" = copy ]; then
  install -m 755 "$src" "$dest"
else
  ln -sfn "$src" "$dest"
fi
printf 'installed %s -> %s\n' "$dest" "$src"

case ":${PATH-}:" in
  *":$dest_dir:"*) ;;
  *) printf '%s is not on PATH; add it to your shell profile\n' "$dest_dir" >&2 ;;
esac

printf '\nwaybar does not inherit your shell PATH. Use the absolute path in every\n'
printf 'exec and on-click, for example:\n\n'
printf '  "exec": "%s status blocked"\n\n' "$dest"

printf 'waybar modules: %s\n' "$here/examples/waybar-config.jsonc"
printf 'waybar css:     %s\n' "$here/examples/style.css"
printf 'config example: %s\n' "$here/examples/config.json"
