# herdr-watchr

Live [herdr](https://github.com/ogulcancelik/herdr) agent status in waybar, and
click to jump to an agent.

One module per status — blocked, idle, done, working, unknown — each a coloured
glyph and a count, tooltipped with that status's agents by workspace and task.
Empty statuses hide; the whole card collapses when no agents are running.

## Requirements

- `herdr` on `PATH`, or `herdr_bin` set in the config.
- Python 3.9+, standard library only.
- A Nerd Font in your bar — the default glyphs are Material Design codepoints
  from its range. Override `waybar.icons` otherwise.
- Hyprland, for the click-to-focus window raise. Other compositors need a
  different `focus_window_cmd`, or `null` to skip the raise.

## Install

```sh
git clone https://github.com/phillhood/herdr-watchr
cd herdr-watchr
./waybar/install.sh
pkill -x waybar && waybar &
```

That installs the binary to `~/.local/bin`, writes `herdr-watchr.jsonc` and
`herdr-watchr.css` into your waybar config directory, and wires both into your
`config.jsonc` and `style.css`. Your files are backed up first and only ever gain
marker-delimited lines, so comments and formatting survive.

The restart is separate on purpose: `SIGUSR2` reloads styling but does not start
newly added modules, and killing a bar that has no respawn supervisor would leave
you with no bar at all. The installer signals waybar and tells you to restart.

| Flag | Effect |
|---|---|
| `--position left\|center\|right` | Which `modules-*` list the group joins. Default `center` |
| `--copy` | Copy the script instead of symlinking it |
| `--force` | Proceed even if the config already wires herdr-watchr by hand |
| `--uninstall` | Remove every change, restoring your files byte-for-byte |

Set `HERDR_WATCHR_PREFIX` to install the binary somewhere other than `~/.local/bin`.

The installer refuses, changing nothing, whenever it cannot be certain: no waybar
config, a multi-bar config, a missing `modules-*` list, an `include` that is a
string rather than an array, or a file it cannot parse. In each case it says what
to add by hand — see [`waybar/examples/`](waybar/examples/) for the full snippets.

If your `config.jsonc` is a symlink into a dotfiles repo, the installer follows it,
edits the real file in place, and prints the path it actually changed. The symlink
survives, so stow stays intact.

## Subcommands

| Subcommand | Behaviour |
|---|---|
| `status <name>` | Emit one status module's JSON and exit |
| `focus-status <name>` | Focus an agent in `<name>`, then raise the terminal window |
| `notify` | Poll herdr and raise `SIGRTMIN+signal` when the displayed state changes |

`notify` is the hidden module in the group. herdr publishes status events per
pane with no global "anything changed" subscription, so it polls and signals the
other five to re-render, rather than each running its own timer.

## Configuration

`~/.config/herdr-watchr/config.json`, every key optional.
[`contract/config.schema.json`](contract/config.schema.json) describes the whole
surface and holds the defaults below. The schema is advisory by design — nothing
validates your file against it, so an out-of-range `signal` or an unknown key is
accepted as written. A file that will not parse, a non-object top level, and a
host section that is not an object each warn once on stderr and fall back to
defaults.

Resolution runs env var → host section → shared trunk → built-in default,
deep-merged per key, so `{"colors": {"blocked": "#ff0000"}}` recolours one status
and leaves the other four alone.

| Key | Default | Meaning |
|---|---|---|
| `urgency` | `["blocked","idle","done","working","unknown"]` | Left-to-right order. Must be a permutation of all five, or it is ignored |
| `colors.<status>` | neutral palette | Glyph colour |
| `poll_seconds` | `1.5` | How often `notify` re-checks herdr |
| `herdr_bin` | `null` | Path to `herdr`; falls back to `PATH`, then `~/.local/bin/herdr` |
| `waybar.icons.<status>` | Material Design glyphs | Glyph rendered in the module |
| `waybar.signal` | `8` | `SIGRTMIN+n` raised by `notify`, matching each module's `signal` |
| `waybar.click_action` | `"first"` | `first` focuses the group's first agent; `cycle` advances through them |
| `waybar.terminal.title` | `"herdr"` | Preferred window title when locating the terminal |
| `waybar.terminal.class` | `"com.mitchellh.ghostty"` | Window class fallback |
| `waybar.focus_window_cmd` | `["hyprctl","dispatch","focuswindow","address:{addr}"]` | Templated argv; `{addr}` is substituted per element. `null` skips the raise |

| Env var | Overrides |
|---|---|
| `HERDR_WATCHR_CONFIG` | Config file path |
| `HERDR_WATCHR_BIN` | `herdr_bin` (`HERDR_BIN` accepted as a fallback) |
| `HERDR_WATCHR_POLL` | `poll_seconds` |
| `HERDR_WATCHR_SIGNAL` | `waybar.signal` |

If you change `HERDR_WATCHR_SIGNAL`, change each module's `signal` to match or
the bar stops updating.

[`waybar/examples/config.json`](waybar/examples/config.json) is the author's own:
Catppuccin Macchiato, `cycle`, and the Hyprland Lua-config focus form.

## The contract

[`contract/`](contract/) is the normative description of how agents are
classified, ordered and selected, plus a fixture suite pinning every case. It
exists because a native macOS menu bar host is planned, and two implementations
of the same behaviour drift unless something binds them. The test suite iterates
`contract/fixtures/`, so adding a fixture extends coverage automatically.

Only the waybar host is built today.

## Tests

```sh
python3 -m unittest discover -s waybar/tests -v
```

## License

MIT. See [LICENSE](LICENSE).
