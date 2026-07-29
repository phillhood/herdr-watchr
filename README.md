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
```

That symlinks `herdr-watchr` into `~/.local/bin`. Pass `--copy` to copy instead,
or set `HERDR_WATCHR_PREFIX` to install somewhere else.

**Use the absolute path in waybar, not the bare command.** waybar runs modules
with the environment it was launched from, which for a compositor autostart or a
display manager routinely excludes `~/.local/bin` — even when your interactive
shell has it. A bare `herdr-watchr` then resolves to nothing and the modules
simply never appear, with no error in the bar. The installer prints the exact
line to use; the examples below assume the default `~/.local/bin`.

Then wire up waybar, in three edits to `~/.config/waybar/`:

**1. Add the group and its six modules** to `config.jsonc`. Copy them from
[`waybar/examples/waybar-config.jsonc`](waybar/examples/waybar-config.jsonc) —
one hidden watcher plus five status modules, all following the same shape:

```jsonc
"group/herdr-watchr": {
  "orientation": "inherit",
  "modules": [
    "custom/herdr-watchr-notify",
    "custom/herdr-blocked",
    "custom/herdr-idle",
    "custom/herdr-done",
    "custom/herdr-working",
    "custom/herdr-unknown"
  ]
},

"custom/herdr-blocked": {
  "exec": "~/.local/bin/herdr-watchr status blocked",
  "return-type": "json",
  "format": "{}",
  "hide-empty-text": true,
  "tooltip": true,
  "signal": 8,
  "on-click": "~/.local/bin/herdr-watchr focus-status blocked"
}
```

**2. Add `"group/herdr-watchr"`** to one of your `modules-left`,
`modules-center` or `modules-right` lists.

**3. Append [`waybar/examples/style.css`](waybar/examples/style.css)** to your
stylesheet. Keep the padding on the child selectors rather than moving it up to
`#herdr-watchr` — that is what lets the card collapse when every status is
empty.

Then reload waybar — `pkill -SIGUSR2 waybar`, or restart it if the modules don't
appear.

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
