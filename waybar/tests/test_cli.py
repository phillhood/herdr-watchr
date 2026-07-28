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


class TestFocusStatusCommand(CliCase):
    def test_it_focuses_the_selected_target(self):
        cfg = hw.load_config(env=MISSING)
        cfg["click_action"] = "cycle"
        agents = [agent("blocked", pane="w2:p1", tid="t3"),
                  agent("blocked", pane="w5:p1", tid="t9")]
        agents[0]["focused"] = True
        with mock.patch.object(hw, "load_config", return_value=cfg), \
             mock.patch.object(hw, "fetch_agents", return_value=agents), \
             mock.patch.object(hw, "focus_agent") as focus:
            hw.cmd_focus_status("blocked")
        focus.assert_called_once_with(cfg, "t9")

    def test_an_empty_status_focuses_nothing(self):
        with mock.patch.object(hw, "load_config",
                               return_value=hw.load_config(env=MISSING)), \
             mock.patch.object(hw, "fetch_agents", return_value=[]), \
             mock.patch.object(hw, "focus_agent") as focus:
            hw.cmd_focus_status("blocked")
        focus.assert_not_called()

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
