import json
import unittest
from unittest import mock

import support

hw = support.load_script()
TERMINAL = {"class": "com.mitchellh.ghostty", "title": "herdr"}
LUA_CMD = ["hyprctl", "dispatch", 'hl.dsp.focus({window="address:{addr}"})']


class FocusCase(unittest.TestCase):
    def setUp(self):
        hw._WARNED.clear()


class TestWindowDiscovery(FocusCase):
    def test_a_title_match_is_preferred(self):
        clients = [{"title": "nvim", "class": "com.mitchellh.ghostty", "address": "0x1"},
                   {"title": "herdr", "class": "com.mitchellh.ghostty", "address": "0x2"}]
        self.assertEqual(hw.pick_herdr_window(clients, TERMINAL)["address"], "0x2")

    def test_a_class_match_is_the_fallback(self):
        clients = [{"title": "nvim", "class": "com.mitchellh.ghostty", "address": "0x1"},
                   {"title": "firefox", "class": "firefox", "address": "0x9"}]
        self.assertEqual(hw.pick_herdr_window(clients, TERMINAL)["address"], "0x1")

    def test_nothing_matching_returns_none(self):
        self.assertIsNone(hw.pick_herdr_window([{"title": "x", "class": "y"}],
                                               TERMINAL))

    def test_an_empty_client_list_returns_none(self):
        self.assertIsNone(hw.pick_herdr_window([], TERMINAL))

    def test_an_empty_terminal_section_matches_nothing(self):
        clients = [{"title": "nvim", "class": "com.mitchellh.ghostty", "address": "0x1"}]
        self.assertIsNone(hw.pick_herdr_window(clients, {}))


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


class TestRaiseTerminalWindow(FocusCase):
    def test_a_null_template_skips_the_client_query(self):
        with mock.patch.object(hw.subprocess, "run") as run:
            hw.raise_terminal_window({"focus_window_cmd": None, "terminal": TERMINAL})
        run.assert_not_called()

    def test_it_queries_clients_then_dispatches_the_rendered_command(self):
        clients = json.dumps([{"title": "herdr", "class": "com.mitchellh.ghostty",
                               "address": "0xfeed"}])
        cfg = {"focus_window_cmd": LUA_CMD, "terminal": TERMINAL}
        with mock.patch.object(hw.subprocess, "run",
                               return_value=mock.Mock(stdout=clients)) as run:
            hw.raise_terminal_window(cfg)
        self.assertEqual(run.call_args_list[0].args[0], ["hyprctl", "-j", "clients"])
        self.assertEqual(run.call_args_list[1].args[0][2],
                         'hl.dsp.focus({window="address:0xfeed"})')

    def test_no_matching_window_dispatches_nothing(self):
        clients = json.dumps([{"title": "firefox", "class": "firefox",
                               "address": "0x9"}])
        cfg = {"focus_window_cmd": LUA_CMD, "terminal": TERMINAL}
        with mock.patch.object(hw.subprocess, "run",
                               return_value=mock.Mock(stdout=clients)) as run:
            hw.raise_terminal_window(cfg)
        self.assertEqual(len(run.call_args_list), 1)

    def test_a_missing_hyprctl_does_not_raise(self):
        cfg = {"focus_window_cmd": LUA_CMD, "terminal": TERMINAL}
        with mock.patch.object(hw.subprocess, "run", side_effect=FileNotFoundError()):
            hw.raise_terminal_window(cfg)

    def test_unparseable_client_json_does_not_raise(self):
        cfg = {"focus_window_cmd": LUA_CMD, "terminal": TERMINAL}
        with mock.patch.object(hw.subprocess, "run",
                               return_value=mock.Mock(stdout="nope")):
            hw.raise_terminal_window(cfg)


class TestFocusAgent(FocusCase):
    def test_no_terminal_id_does_nothing(self):
        cfg = {"herdr_bin": "/opt/herdr", "focus_window_cmd": None}
        with mock.patch.object(hw.subprocess, "run") as run:
            hw.focus_agent(cfg, None)
        run.assert_not_called()

    def test_it_focuses_the_agent_with_a_three_second_timeout(self):
        cfg = {"herdr_bin": "/opt/herdr", "focus_window_cmd": None,
               "terminal": TERMINAL}
        with mock.patch.object(hw.subprocess, "run") as run:
            hw.focus_agent(cfg, "t9")
        self.assertEqual(run.call_args.args[0],
                         ["/opt/herdr", "agent", "focus", "t9"])
        self.assertEqual(run.call_args.kwargs["timeout"], 3)

    def test_a_failing_focus_still_raises_the_window(self):
        clients = json.dumps([{"title": "herdr", "class": "com.mitchellh.ghostty",
                               "address": "0xfeed"}])
        cfg = {"herdr_bin": "/opt/herdr", "focus_window_cmd": LUA_CMD,
               "terminal": TERMINAL}
        calls = []

        def run(argv, **kwargs):
            calls.append(argv)
            if argv[0] == "/opt/herdr":
                raise OSError("boom")
            return mock.Mock(stdout=clients)

        with mock.patch.object(hw.subprocess, "run", side_effect=run):
            hw.focus_agent(cfg, "t9")
        self.assertEqual(len(calls), 3)


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
