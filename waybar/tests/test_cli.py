import contextlib
import io
import json
import unittest
from unittest import mock

import support

hw = support.load_script()
MISSING = {"HERDR_WATCHR_CONFIG": "/nonexistent/herdr-watchr/config.json"}


def agent(status, pane="w1:p1", tid="t1"):
    return {"agent_status": status, "pane_id": pane, "terminal_id": tid,
            "workspace_id": "w1", "terminal_title_stripped": "task"}


class CliCase(unittest.TestCase):
    def setUp(self):
        hw._WARNED.clear()


class TestDispatch(CliCase):
    def test_status_dispatches_with_the_name(self):
        with mock.patch.object(hw, "cmd_status") as cmd:
            self.assertEqual(hw.main(["herdr-watchr", "status", "blocked"]), 0)
        cmd.assert_called_once_with("blocked")

    def test_focus_status_dispatches_with_the_name(self):
        with mock.patch.object(hw, "cmd_focus_status") as cmd:
            self.assertEqual(hw.main(["herdr-watchr", "focus-status", "idle"]), 0)
        cmd.assert_called_once_with("idle")

    def test_notify_dispatches(self):
        with mock.patch.object(hw, "cmd_notify") as cmd:
            self.assertEqual(hw.main(["herdr-watchr", "notify"]), 0)
        cmd.assert_called_once_with()

    def test_no_argument_defaults_to_notify(self):
        with mock.patch.object(hw, "cmd_notify") as cmd:
            self.assertEqual(hw.main(["herdr-watchr"]), 0)
        cmd.assert_called_once_with()

    def test_status_without_a_name_is_a_usage_error(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(hw.main(["herdr-watchr", "status"]), 2)
        self.assertIn("usage:", err.getvalue())

    def test_an_unknown_subcommand_is_a_usage_error(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(hw.main(["herdr-watchr", "wat"]), 2)


class TestStatusCommand(CliCase):
    def test_it_emits_the_rendered_module(self):
        out = io.StringIO()
        with mock.patch.dict(hw.os.environ, MISSING, clear=False), \
             mock.patch.object(hw, "fetch_agents", return_value=[agent("blocked")]), \
             contextlib.redirect_stdout(out):
            hw.cmd_status("blocked")
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["class"], ["herdr-watchr", "blocked"])
        self.assertTrue(payload["text"].endswith(" 1"))

    def test_an_internal_failure_still_emits_valid_hidden_json(self):
        out = io.StringIO()
        with mock.patch.object(hw, "load_config", side_effect=RuntimeError("boom")), \
             contextlib.redirect_stdout(out), \
             contextlib.redirect_stderr(io.StringIO()):
            hw.cmd_status("blocked")
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["text"], "")
        self.assertIn("empty", payload["class"])

    def test_an_internal_failure_is_reported_on_stderr(self):
        err = io.StringIO()
        with mock.patch.object(hw, "load_config", side_effect=RuntimeError("boom")), \
             contextlib.redirect_stdout(io.StringIO()), \
             contextlib.redirect_stderr(err):
            hw.cmd_status("blocked")
        self.assertIn("boom", err.getvalue())

    def test_a_scalar_where_colors_should_be_still_emits_valid_json(self):
        out = io.StringIO()
        cfg = hw.load_config(env=MISSING)
        cfg["colors"] = "purple"
        with mock.patch.object(hw, "load_config", return_value=cfg), \
             mock.patch.object(hw, "fetch_agents", return_value=[agent("blocked")]), \
             contextlib.redirect_stdout(out), \
             contextlib.redirect_stderr(io.StringIO()):
            hw.cmd_status("blocked")
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["text"], "")
        self.assertIn("empty", payload["class"])


SESSIONS = {"sessions": [{"name": "default", "running": True},
                         {"name": "work", "running": True}]}
WORKSPACES = {
    "default": {"result": {"workspaces": [
        {"workspace_id": "w2", "label": "homelab", "focused": True}]}},
    "work": {"result": {"workspaces": [
        {"workspace_id": "w1", "label": "helios", "focused": True}]}},
}
CLIENTS = [{"address": "0xhome", "title": "chorrol: homelab",
            "class": "com.mitchellh.ghostty", "focusHistoryID": 0},
           {"address": "0xwork", "title": "chorrol: helios",
            "class": "com.mitchellh.ghostty", "focusHistoryID": 2}]


def tagged(status, pane, tid, session, focused=False, ws="w1"):
    return {"agent_status": status, "pane_id": pane, "terminal_id": tid,
            "workspace_id": ws, "session": session, "focused": focused,
            "terminal_title_stripped": "task"}


class TestFocusStatusCommand(CliCase):
    def test_first_without_a_raise_command_queries_no_workspaces(self):
        cfg = hw.load_config(env=MISSING)
        cfg["focus_window_cmd"] = None
        target = tagged("idle", "w1:p1", "t3", "work")
        with mock.patch.object(hw, "load_config", return_value=cfg), \
             mock.patch.object(hw, "list_sessions", return_value=["work"]), \
             mock.patch.object(hw, "fetch_agents", return_value=[target]), \
             mock.patch.object(hw, "load_workspaces") as load, \
             mock.patch.object(hw, "focus_agent"):
            hw.cmd_focus_status("idle")
        load.assert_not_called()

    def run_click(self, name, click_action, agents, active_title):
        cfg = hw.load_config(env=MISSING)
        cfg["herdr_bin"] = "/opt/herdr"
        cfg["click_action"] = click_action
        cfg["focus_window_cmd"] = ["raise", "{addr}", "{session}"]
        by_session = {"default": [], "work": []}
        for agent in agents:
            by_session[agent["session"]].append(
                dict((k, v) for k, v in agent.items() if k != "session"))
        responses = {
            ("/opt/herdr", "session", "list", "--json"): SESSIONS,
            ("hyprctl", "-j", "activewindow"): {"title": active_title},
            ("hyprctl", "-j", "clients"): CLIENTS,
        }
        for session, items in by_session.items():
            responses[("/opt/herdr", "--session", session, "agent", "list")] = \
                {"result": {"agents": items}}
            responses[("/opt/herdr", "--session", session, "workspace", "list")] = \
                WORKSPACES[session]
        calls = []

        def run(argv, **kwargs):
            calls.append(argv)
            value = responses.get(tuple(argv))
            return mock.Mock(stdout=json.dumps(value) if value is not None else "")

        with mock.patch.object(hw, "load_config", return_value=cfg), \
             mock.patch.object(hw.socket, "gethostname", return_value="chorrol"), \
             mock.patch.object(hw.subprocess, "run", side_effect=run):
            hw.cmd_focus_status(name)
        return calls

    def test_cycle_in_the_active_session_raises_that_sessions_window(self):
        agents = [tagged("blocked", "w2:p1", "t1", "default", focused=True, ws="w2"),
                  tagged("blocked", "w5:p1", "t2", "default", ws="w5"),
                  tagged("blocked", "w1:p1", "t3", "work", focused=True)]
        calls = self.run_click("blocked", "cycle", agents, "chorrol: helios")
        self.assertIn(["/opt/herdr", "--session", "default", "agent", "focus", "t1"],
                      calls)
        self.assertEqual(calls[-1], ["raise", "0xhome", "default"])

    def test_a_work_agent_raises_the_work_window(self):
        agents = [tagged("idle", "w1:p1", "t3", "work")]
        calls = self.run_click("idle", "first", agents, "chorrol: homelab")
        self.assertIn(["/opt/herdr", "--session", "work", "agent", "focus", "t3"],
                      calls)
        self.assertEqual(calls[-1], ["raise", "0xwork", "work"])

    def test_the_window_is_looked_up_before_the_agent_is_focused(self):
        agents = [tagged("idle", "w1:p1", "t3", "work")]
        calls = self.run_click("idle", "first", agents, "chorrol: homelab")
        self.assertLess(calls.index(["hyprctl", "-j", "clients"]),
                        calls.index(["/opt/herdr", "--session", "work",
                                     "agent", "focus", "t3"]))

    def test_first_does_not_query_the_active_window(self):
        agents = [tagged("idle", "w1:p1", "t3", "work")]
        calls = self.run_click("idle", "first", agents, "chorrol: homelab")
        self.assertNotIn(["hyprctl", "-j", "activewindow"], calls)

    def test_an_empty_status_focuses_nothing(self):
        agents = [tagged("idle", "w1:p1", "t3", "work")]
        calls = self.run_click("blocked", "first", agents, "chorrol: homelab")
        self.assertFalse(any("focus" in argv for argv in calls))
        self.assertFalse(any("workspace" in argv for argv in calls))

    def test_a_null_focus_window_cmd_skips_the_client_query(self):
        cfg = hw.load_config(env=MISSING)
        cfg["focus_window_cmd"] = None
        target = tagged("idle", "w1:p1", "t3", "work")
        with mock.patch.object(hw, "load_config", return_value=cfg), \
             mock.patch.object(hw, "list_sessions", return_value=["work"]), \
             mock.patch.object(hw, "fetch_agents", return_value=[target]), \
             mock.patch.object(hw, "load_workspaces", return_value={}), \
             mock.patch.object(hw, "find_terminal_window") as find, \
             mock.patch.object(hw, "focus_agent") as focus:
            hw.cmd_focus_status("idle")
        find.assert_not_called()
        focus.assert_called_once_with(cfg, target, None)

    def test_an_internal_failure_does_not_raise(self):
        with mock.patch.object(hw, "load_config", side_effect=RuntimeError("boom")), \
             contextlib.redirect_stderr(io.StringIO()):
            hw.cmd_focus_status("blocked")


class TestNotifyCommand(CliCase):
    def test_it_signals_only_when_the_state_changes(self):
        cfg = hw.load_config(env=MISSING)
        states = [[agent("idle")], [agent("idle")], [agent("blocked")]]
        signals = []

        def sleep(_seconds):
            if not states:
                raise KeyboardInterrupt

        with mock.patch.object(hw, "load_config", return_value=cfg), \
             mock.patch.object(hw, "fetch_agents",
                               side_effect=lambda _cfg: states.pop(0)), \
             mock.patch.object(hw, "nudge", side_effect=signals.append), \
             mock.patch.object(hw.time, "sleep", side_effect=sleep), \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(KeyboardInterrupt):
                hw.cmd_notify()
        self.assertEqual(signals, [8, 8])

    def test_it_emits_a_hidden_module_before_polling(self):
        out = io.StringIO()
        with mock.patch.object(hw, "load_config",
                               return_value=hw.load_config(env=MISSING)), \
             mock.patch.object(hw, "fetch_agents", return_value=[]), \
             mock.patch.object(hw, "nudge"), \
             mock.patch.object(hw.time, "sleep", side_effect=KeyboardInterrupt), \
             contextlib.redirect_stdout(out):
            with self.assertRaises(KeyboardInterrupt):
                hw.cmd_notify()
        payload = json.loads(out.getvalue().splitlines()[0])
        self.assertEqual(payload["text"], "")

    def test_a_fetch_failure_does_not_end_the_loop(self):
        cfg = hw.load_config(env=MISSING)
        attempts = []

        def fetch(_cfg):
            attempts.append(1)
            if len(attempts) == 1:
                raise RuntimeError("boom")
            return [agent("idle")]

        def sleep(_seconds):
            if len(attempts) >= 2:
                raise KeyboardInterrupt

        with mock.patch.object(hw, "load_config", return_value=cfg), \
             mock.patch.object(hw, "fetch_agents", side_effect=fetch), \
             mock.patch.object(hw, "nudge") as nudge, \
             mock.patch.object(hw.time, "sleep", side_effect=sleep), \
             contextlib.redirect_stdout(io.StringIO()), \
             contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(KeyboardInterrupt):
                hw.cmd_notify()
        nudge.assert_called_once_with(8)


if __name__ == "__main__":
    unittest.main()
