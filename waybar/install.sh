#!/usr/bin/env bash
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
src="$here/herdr-watchr"
dest_dir="${HERDR_WATCHR_PREFIX:-$HOME/.local/bin}"
dest="$dest_dir/herdr-watchr"
config_home="${XDG_CONFIG_HOME:-$HOME/.config}"
waybar_dir="$config_home/waybar"
mode=symlink
position=center
action=install
force_flag=""

while [ $# -gt 0 ]; do
  case "$1" in
    --copy) mode=copy ;;
    --uninstall) action=uninstall ;;
    --force) force_flag=--force ;;
    --position)
      if [ $# -lt 2 ]; then
        printf 'install.sh: --position needs a value\n' >&2
        exit 2
      fi
      position="$2"
      shift
      ;;
    -h|--help)
      printf 'usage: install.sh [--copy] [--position left|center|right] [--force] [--uninstall]\n'
      exit 0
      ;;
    *) printf 'install.sh: unknown option %s\n' "$1" >&2; exit 2 ;;
  esac
  shift
done

stamp="$(date +%s)"

remove_binary() {
  if [ -L "$dest" ] && [ "$(readlink -f "$dest")" = "$(readlink -f "$src")" ]; then
    rm -f "$dest"
    printf 'removed %s\n' "$dest"
  elif [ -f "$dest" ] && cmp -s "$dest" "$src"; then
    rm -f "$dest"
    printf 'removed %s\n' "$dest"
  elif [ -e "$dest" ]; then
    printf 'left %s in place; it was not installed by this script\n' "$dest" >&2
  fi
}

if [ "$action" = uninstall ]; then
  python3 "$here/wire.py" uninstall --waybar-dir "$waybar_dir" --stamp "$stamp"
  remove_binary
  printf 'restart waybar to drop the modules\n'
  exit 0
fi

case "$position" in
  left|center|right) ;;
  *) printf 'install.sh: position must be left, center or right\n' >&2; exit 2 ;;
esac

mkdir -p "$dest_dir"
if [ "$mode" = copy ]; then
  install -m 755 "$src" "$dest"
else
  ln -sfn "$src" "$dest"
fi
printf 'installed %s -> %s\n' "$dest" "$src"

python3 "$here/wire.py" install --waybar-dir "$waybar_dir" --binary "$dest" \
  --position "$position" --stamp "$stamp" ${force_flag:+"$force_flag"}

pkill -SIGUSR2 waybar 2>/dev/null || true

printf '\nnew modules need a full waybar restart:\n'
printf '  pkill -x waybar && waybar &\n\n'
printf 'optional config: %s/herdr-watchr/config.json\n' "$config_home"
printf 'every setting:   %s/contract/config.schema.json\n' "$(cd "$here/.." && pwd)"

case ":${PATH-}:" in
  *":$dest_dir:"*) ;;
  *) printf '%s is not on PATH; waybar uses the absolute path, but your shell will not find it\n' "$dest_dir" >&2 ;;
esac
