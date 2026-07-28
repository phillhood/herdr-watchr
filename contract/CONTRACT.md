# The herdr-watchr contract

Two implementations render herdr agent status: a Python waybar element and a
Swift menu bar app. This document binds the four things a second implementation
can get subtly wrong without any test noticing. Everything else — rendering,
update mechanism, window raising, error presentation — is host-specific and
outside the contract.

Both hosts' test suites iterate `fixtures/` rather than enumerating cases, so
adding a fixture file automatically extends both. That is why the contract is
data and not only prose.

## 1. Status vocabulary

Exactly five statuses:

    blocked | idle | done | working | unknown

An agent's status is the value of `agent_status`. Any other value, a null value,
and a missing key all map to `unknown`. The comparison is case-sensitive:
`"IDLE"` is not `idle`, it is `unknown`.

## 2. Status display order

Statuses render in `urgency` order. A status whose count is zero renders
nothing at all.

`urgency` is configurable, but only as a permutation: a list that is not exactly
the five vocabulary members is rejected and the default order is used.

The hosts reach the zero-count end state differently — waybar emits an empty
`text` and lets `hide-empty-text` collapse the module, macOS omits the segment
from its attributed title. The contract binds the outcome, not the mechanism.

## 3. Agent order within a status

Stable sort by `pane_id` ascending, comparing the raw string. `pane_id` looks
like `w10:p1`, so the ordering is lexicographic, not numeric: `w10:p1` sorts
before `w2:p1`.

This is what stops a status's first agent jumping when an unrelated agent
changes state, and it is load-bearing for click targeting.

## 4. Click target selection

Given a status group already in contract order, and `click_action`:

- `first` selects `matching[0]`.
- `cycle` selects `matching[(i + 1) % n]`, where *i* is the index within the
  group of the agent whose `focused` is true. When no agent in the group is
  focused — including when the focused agent is in a different status, or when
  no agent anywhere is focused — it falls back to `matching[0]`.
- An empty group selects nothing.

Any `click_action` value other than `cycle` behaves as `first`.

## Fixture format

Each file in `fixtures/` is one captured `herdr agent list` payload plus its
expected outcome.

    {
      "name": "human-readable description of the case",
      "agents": [ ... raw agent objects as herdr emits them ... ],
      "expected": {
        "order":  ["blocked"],
        "counts": {"blocked": 2},
        "agents": {"blocked": ["w2:p1", "w5:p1"]},
        "first_target": {"status": "blocked", "expect": "w2:p1"},
        "cycle_target": {"status": "blocked", "expect": "w5:p1"}
      }
    }

`order`, `counts` and `agents` name only the statuses with a non-zero count.
`agents` maps a status to its `pane_id`s in contract order. `first_target` and
`cycle_target` each name a status to query and the `pane_id` expected back;
`"expect": null` means the group is empty and nothing is selected. Both target
keys are required, and `expected` carries no other keys.

## Configuration

`config.schema.json` describes every setting and carries its default value. Both
hosts resolve configuration in this order, highest first:

    env var  ->  host section  ->  shared trunk  ->  built-in default

Deep-merged per key, so `{"colors": {"blocked": "#ff0000"}}` overrides one status
and leaves the other four at their defaults. A host section may override any
shared key, which is how a different palette per platform works.

Neither host treats a validation failure as fatal. A malformed config warns once
and falls back to defaults.
