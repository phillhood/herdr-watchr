import json
import unittest
from unittest import mock

import support

hw = support.load_script()
TERMINAL = {"class": "com.mitchellh.ghostty", "title": "{hostname}: {workspace}"}
GHOSTTY = "com.mitchellh.ghostty"
WORKSPACES = {
    "default": [{"workspace_id": "w1", "label": "homelab", "focused": True},
                {"workspace_id": "w8", "label": "dotfiles", "focused": False}],
    "work": [{"workspace_id": "w1", "label": "helios", "focused": True}],
}


def client(addr, title, history, cls=GHOSTTY):
    return {"address": addr, "title": title, "class": cls,
            "focusHistoryID": history}
LUA_CMD = ["hyprctl", "dispatch", 'hl.dsp.focus({window="address:{addr}"})']


class FocusCase(unittest.TestCase):
    def setUp(self):
        hw._WARNED.clear()


class TestRenderTitle(FocusCase):
    def test_every_token_is_substituted(self):
        self.assertEqual(hw.render_title("{hostname}: {workspace} [{session}]",
                                         "chorrol", "helios", "work"),
                         "chorrol: helios [work]")

    def test_a_literal_title_renders_as_itself(self):
        self.assertEqual(hw.render_title("herdr", "chorrol", "helios", "work"),
                         "herdr")

    def test_an_unsupported_token_is_left_in_place(self):
        self.assertEqual(hw.render_title("{tab}", "chorrol", "helios", "work"),
                         "{tab}")

    def test_a_non_string_template_renders_nothing(self):
        self.assertIsNone(hw.render_title(None, "chorrol", "helios", "work"))


class TestSessionTitles(FocusCase):
    def test_the_focused_label_and_the_target_label_are_both_candidates(self):
        self.assertEqual(
            hw.session_titles(TERMINAL["title"], "chorrol", "default",
                              WORKSPACES["default"], "w8"),
            {"chorrol: homelab", "chorrol: dotfiles"})

    def test_an_unknown_target_workspace_adds_nothing(self):
        self.assertEqual(
            hw.session_titles(TERMINAL["title"], "chorrol", "default",
                              WORKSPACES["default"], "w99"),
            {"chorrol: homelab"})

    def test_missing_workspaces_predict_nothing(self):
        self.assertEqual(hw.session_titles(TERMINAL["title"], "chorrol", "work",
                                           None, "w1"), set())

    def test_a_literal_title_needs_no_workspaces(self):
        self.assertEqual(hw.session_titles("herdr", "chorrol", "work", None),
                         {"herdr"})

    def test_an_untagged_session_renders_as_empty(self):
        self.assertEqual(hw.session_titles("h-{session}", "chorrol", None, None),
                         {"h-"})

    def test_a_non_string_template_predicts_nothing(self):
        self.assertEqual(hw.session_titles(None, "chorrol", "work",
                                           WORKSPACES["work"]), set())


class TestPickWindow(FocusCase):
    def test_a_title_match_is_preferred(self):
        clients = [client("0x1", "nvim", 0), client("0x2", "chorrol: helios", 3)]
        self.assertEqual(hw.pick_herdr_window(clients, {"chorrol: helios"},
                                              GHOSTTY)["address"], "0x2")

    def test_several_title_matches_pick_the_most_recently_focused(self):
        clients = [client("0x1", "chorrol: x", 4), client("0x2", "chorrol: x", 1)]
        self.assertEqual(hw.pick_herdr_window(clients, {"chorrol: x"},
                                              GHOSTTY)["address"], "0x2")

    def test_no_title_match_falls_back_to_the_most_recent_class_match(self):
        clients = [client("0x1", "a", 3), client("0x2", "b", 0),
                   client("0x9", "c", 1, cls="firefox")]
        self.assertEqual(hw.pick_herdr_window(clients, {"chorrol: x"},
                                              GHOSTTY)["address"], "0x2")

    def test_a_missing_focus_history_sorts_last(self):
        clients = [{"address": "0x1", "title": "t", "class": GHOSTTY},
                   client("0x2", "t", 5)]
        self.assertEqual(hw.pick_herdr_window(clients, {"t"}, GHOSTTY)["address"],
                         "0x2")

    def test_nothing_matching_returns_none(self):
        self.assertIsNone(hw.pick_herdr_window([client("0x9", "x", 0, cls="y")],
                                               {"t"}, GHOSTTY))

    def test_no_class_and_no_title_match_returns_none(self):
        self.assertIsNone(hw.pick_herdr_window([client("0x1", "x", 0)], set(), None))

    def test_non_object_clients_are_ignored(self):
        self.assertIsNone(hw.pick_herdr_window(["junk"], {"t"}, GHOSTTY))


def hypr_router(responses, calls=None):
    calls = [] if calls is None else calls

    def run(argv, **kwargs):
        calls.append(argv)
        value = responses.get(tuple(argv))
        if isinstance(value, BaseException):
            raise value
        return mock.Mock(stdout=json.dumps(value) if value is not None else "")

    return run, calls


class TestWorkspaces(FocusCase):
    def test_the_workspace_list_is_scoped_to_the_session(self):
        payload = {"result": {"workspaces": WORKSPACES["work"] + ["junk"]}}
        run, calls = hypr_router({
            ("/opt/herdr", "--session", "work", "workspace", "list"): payload})
        with mock.patch.object(hw.subprocess, "run", side_effect=run):
            got = hw.fetch_workspaces({"herdr_bin": "/opt/herdr"}, "work")
        self.assertEqual(got, WORKSPACES["work"])

    def test_a_failing_workspace_list_returns_none(self):
        with mock.patch.object(hw.subprocess, "run", side_effect=FileNotFoundError()):
            self.assertIsNone(hw.fetch_workspaces({"herdr_bin": "/opt/herdr"}, "work"))

    def test_untagged_agents_load_the_unscoped_list(self):
        payload = {"result": {"workspaces": WORKSPACES["work"]}}
        run, _ = hypr_router({("/opt/herdr", "workspace", "list"): payload})
        with mock.patch.object(hw.subprocess, "run", side_effect=run):
            got = hw.load_workspaces({"herdr_bin": "/opt/herdr"}, None)
        self.assertEqual(got, {None: WORKSPACES["work"]})


class TestActiveSession(FocusCase):
    def setUp(self):
        super().setUp()
        self.cfg = {"terminal": TERMINAL}

    def active(self, title, workspaces=WORKSPACES, sessions=("default", "work")):
        run, calls = hypr_router({("hyprctl", "-j", "activewindow"): {"title": title}})
        with mock.patch.object(hw.subprocess, "run", side_effect=run):
            got = hw.find_active_session(self.cfg, list(sessions), workspaces,
                                         "chorrol")
        return got, calls

    def test_the_session_whose_title_is_active_wins(self):
        self.assertEqual(self.active("chorrol: helios")[0], "work")

    def test_an_ambiguous_title_is_no_session(self):
        same = {"default": WORKSPACES["work"], "work": WORKSPACES["work"]}
        self.assertIsNone(self.active("chorrol: helios", workspaces=same)[0])

    def test_an_unrelated_window_is_no_session(self):
        self.assertIsNone(self.active("Mozilla Firefox")[0])

    def test_no_sessions_skip_the_hyprctl_query(self):
        got, calls = self.active("chorrol: helios", sessions=())
        self.assertIsNone(got)
        self.assertEqual(calls, [])

    def test_a_failing_hyprctl_is_no_session(self):
        with mock.patch.object(hw.subprocess, "run", side_effect=FileNotFoundError()):
            self.assertIsNone(hw.find_active_session(self.cfg, ["work"], WORKSPACES,
                                                     "chorrol"))


class TestFindTerminalWindow(FocusCase):
    def test_the_target_sessions_window_is_found(self):
        clients = [client("0xwork", "chorrol: helios", 3),
                   client("0xhome", "chorrol: homelab", 0)]
        run, _ = hypr_router({("hyprctl", "-j", "clients"): clients})
        target = {"session": "work", "workspace_id": "w1"}
        with mock.patch.object(hw.subprocess, "run", side_effect=run):
            window = hw.find_terminal_window({"terminal": TERMINAL}, target,
                                             WORKSPACES, "chorrol")
        self.assertEqual(window["address"], "0xwork")

    def test_a_failing_client_query_finds_nothing(self):
        with mock.patch.object(hw.subprocess, "run", side_effect=FileNotFoundError()):
            self.assertIsNone(hw.find_terminal_window(
                {"terminal": TERMINAL}, {"session": "work"}, WORKSPACES, "chorrol"))


class TestFocusCommandTemplate(FocusCase):
    def test_addr_is_substituted_in_every_element(self):
        template = ["hyprctl", "dispatch", "focuswindow", "address:{addr}"]
        self.assertEqual(hw.render_focus_cmd(template, "0xabc"),
                         ["hyprctl", "dispatch", "focuswindow", "address:0xabc"])

    def test_addr_is_substituted_inside_a_lua_expression(self):
        self.assertEqual(hw.render_focus_cmd(LUA_CMD, "0xabc")[2],
                         'hl.dsp.focus({window="address:0xabc"})')

    def test_a_null_template_renders_nothing(self):
        self.assertEqual(hw.render_focus_cmd(None, "0xabc"), [])

    def test_an_empty_template_renders_nothing(self):
        self.assertEqual(hw.render_focus_cmd([], "0xabc"), [])

    def test_session_is_substituted_in_every_element(self):
        self.assertEqual(hw.render_focus_cmd(["x", "{session}:{addr}"], "0x1", "work"),
                         ["x", "work:0x1"])

    def test_session_defaults_to_empty(self):
        self.assertEqual(hw.render_focus_cmd(["{session}"], "0x1"), [""])


class TestRaiseTerminalWindow(FocusCase):
    def test_a_null_template_runs_nothing(self):
        with mock.patch.object(hw.subprocess, "run") as run:
            hw.raise_terminal_window({"focus_window_cmd": None}, {"address": "0x1"})
        run.assert_not_called()

    def test_no_window_runs_nothing(self):
        with mock.patch.object(hw.subprocess, "run") as run:
            hw.raise_terminal_window({"focus_window_cmd": LUA_CMD}, None)
        run.assert_not_called()

    def test_it_dispatches_the_rendered_command(self):
        with mock.patch.object(hw.subprocess, "run") as run:
            hw.raise_terminal_window({"focus_window_cmd": LUA_CMD},
                                     {"address": "0xfeed"}, "work")
        self.assertEqual(run.call_args.args[0][2],
                         'hl.dsp.focus({window="address:0xfeed"})')
        self.assertEqual(run.call_args.kwargs["timeout"], 3)

    def test_a_missing_hyprctl_does_not_raise(self):
        with mock.patch.object(hw.subprocess, "run", side_effect=FileNotFoundError()):
            hw.raise_terminal_window({"focus_window_cmd": LUA_CMD}, {"address": "0x1"})


class TestFocusAgent(FocusCase):
    def setUp(self):
        super().setUp()
        self.cfg = {"herdr_bin": "/opt/herdr", "focus_window_cmd": ["raise", "{session}"]}

    def test_no_terminal_id_does_nothing(self):
        with mock.patch.object(hw.subprocess, "run") as run:
            hw.focus_agent(self.cfg, {"session": "work"}, {"address": "0x1"})
        run.assert_not_called()

    def test_it_focuses_within_the_agents_session_then_raises(self):
        with mock.patch.object(hw.subprocess, "run") as run:
            hw.focus_agent(self.cfg, {"terminal_id": "t9", "session": "work"},
                           {"address": "0x1"})
        self.assertEqual([c.args[0] for c in run.call_args_list],
                         [["/opt/herdr", "--session", "work", "agent", "focus", "t9"],
                          ["raise", "work"]])
        self.assertEqual(run.call_args_list[0].kwargs["timeout"], 3)

    def test_an_untagged_agent_is_focused_unscoped(self):
        with mock.patch.object(hw.subprocess, "run") as run:
            hw.focus_agent(self.cfg, {"terminal_id": "t9"}, None)
        self.assertEqual(run.call_args.args[0], ["/opt/herdr", "agent", "focus", "t9"])

    def test_a_failing_focus_still_raises_the_window(self):
        calls = []

        def run(argv, **kwargs):
            calls.append(argv)
            if argv[0] == "/opt/herdr":
                raise OSError("boom")
            return mock.Mock(stdout="")

        with mock.patch.object(hw.subprocess, "run", side_effect=run):
            hw.focus_agent(self.cfg, {"terminal_id": "t9", "session": "work"},
                           {"address": "0x1"})
        self.assertEqual(calls[-1], ["raise", "work"])


class TestNudge(FocusCase):
    def test_it_sends_the_configured_realtime_signal(self):
        with mock.patch.object(hw.subprocess, "run") as run:
            hw.nudge(8)
        self.assertEqual(run.call_args.args[0], ["pkill", "-RTMIN+8", "waybar"])

    def test_a_non_integer_signal_does_not_raise(self):
        with mock.patch.object(hw.subprocess, "run") as run:
            hw.nudge("loud")
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
