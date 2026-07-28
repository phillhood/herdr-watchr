# herdr-watchr

Live [herdr](https://github.com/phillhood/herdr) agent status in your system
bar, and click to jump to an agent.

Two hosts share one contract and one config file:

- **waybar** on Linux — one module per status, grouped into a single card that
  collapses to nothing when no agents are running.
- **macOS menu bar** — a native status item. Not built yet.

## Requirements

- `herdr` on `PATH`, or `herdr_bin` set in the config.
- Python 3.9 or newer. No third-party packages.
- A Nerd Font in your bar. The default icons are Material Design glyphs from the
  Nerd Font range; override `waybar.icons` if you use something else.
- Window raising as shipped assumes Hyprland. See `focus_window_cmd` below.

## Install

```
git clone https://github.com/phillhood/herdr-watchr
cd herdr-watchr
./waybar/install.sh
```

This symlinks `herdr-watchr` into `~/.local/bin`; pass `--copy` to copy instead,
or set `HERDR_WATCHR_PREFIX` to install elsewhere. The script prints the paths of
the waybar snippet and CSS to paste.

Add `group/herdr-watchr` to a `modules-*` list in your waybar config, then merge
`waybar/examples/waybar-config.jsonc` and `waybar/examples/style.css` into your
own files.

The padding in the stylesheet sits on the child modules rather than on the
group. That is what lets the whole card collapse to nothing when every status is
empty; moving it up to `#herdr-watchr` leaves a visible empty card.

## Subcommands

| Subcommand | Behaviour |
|---|---|
| `status <name>` | Emit one status module's JSON and exit |
| `focus-status <name>` | Focus an agent in `<name>`, then raise the terminal window |
| `notify` | Poll herdr and raise `SIGRTMIN+signal` when the rendered state changes |

`notify` exists because herdr's agent-status events are per-pane — there is no
global "any agent changed" subscription — so polling `agent list` and signalling
on change is the honest approach, and it avoids a busy timer on every module.

## Configuration

`~/.config/herdr-watchr/config.json`, validated against
[`contract/config.schema.json`](contract/config.schema.json). Nothing here is
required; every key falls back to a default. A malformed file warns once on
stderr and is ignored.

Shared keys sit at the top level, host-specific keys are namespaced, and
resolution runs env var → host section → shared trunk → built-in default,
deep-merged per key. So `{"colors": {"blocked": "#ff0000"}}` changes one status
and leaves the other four alone, and `waybar.colors` beats top-level `colors`.

| Key | Default | Meaning |
|---|---|---|
| `urgency` | `["blocked","idle","done","working","unknown"]` | Left-to-right order. Must be a permutation of all five, or it is ignored |
| `colors.<status>` | neutral palette | Glyph color |
| `poll_seconds` | `1.5` | How often `notify` re-checks herdr |
| `herdr_bin` | `null` | Path to `herdr`; falls back to `PATH`, then `~/.local/bin/herdr` |
| `waybar.icons.<status>` | Material Design glyphs | Glyph rendered in the module |
| `waybar.signal` | `8` | `SIGRTMIN+n` raised by `notify` and carried by each module |
| `waybar.click_action` | `"first"` | `first` focuses the group's first agent; `cycle` advances through them |
| `waybar.terminal.title` | `"herdr"` | Preferred window title when locating the terminal |
| `waybar.terminal.class` | `"com.mitchellh.ghostty"` | Window class fallback |
| `waybar.focus_window_cmd` | `["hyprctl","dispatch","focuswindow","address:{addr}"]` | Templated argv; `{addr}` is substituted per element. `null` skips raising and focuses the herdr pane only |

| Env var | Overrides |
|---|---|
| `HERDR_WATCHR_CONFIG` | Config file path |
| `HERDR_WATCHR_BIN` | `herdr_bin` (`HERDR_BIN` accepted as a fallback) |
| `HERDR_WATCHR_POLL` | `poll_seconds` |
| `HERDR_WATCHR_SIGNAL` | `waybar.signal` |

`waybar/examples/config.json` is the author's own file: Catppuccin Macchiato,
`cycle`, and the Hyprland Lua-config focus form.

## The contract

[`contract/CONTRACT.md`](contract/CONTRACT.md) binds the four behaviours both
hosts must agree on: the status vocabulary, display order, agent order within a
status, and click-target selection. `contract/fixtures/` holds captured agent
lists with their expected outcomes; both hosts' test suites iterate the
directory, so adding a fixture extends both.

## Tests

```
python3 -m unittest discover -s waybar/tests -v
```

## License

MIT. See [LICENSE](LICENSE).
