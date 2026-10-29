import json
import os
import unittest
from unittest import mock

import support

hw = support.load_script()


def completed(stdout):
    return mock.Mock(stdout=stdout, stderr="", returncode=0)


class TestFetchAgents(unittest.TestCase):
    def setUp(self):
        hw._WARNED.clear()
        self.cfg = {"herdr_bin": "/opt/herdr"}

    def test_the_agent_list_envelope_is_unwrapped(self):
        payload = json.dumps({"result": {"agents": [{"pane_id": "w1:p1"}]}})
        with mock.patch.object(hw.subprocess, "run", return_value=completed(payload)):
            self.assertEqual(hw.fetch_agents(self.cfg), [{"pane_id": "w1:p1"}])

    def test_an_empty_agent_list_is_returned_as_is(self):
        payload = json.dumps({"result": {"agents": []}})
        with mock.patch.object(hw.subprocess, "run", return_value=completed(payload)):
            self.assertEqual(hw.fetch_agents(self.cfg), [])

    def test_a_missing_result_key_yields_empty(self):
        with mock.patch.object(hw.subprocess, "run", return_value=completed("{}")):
            self.assertEqual(hw.fetch_agents(self.cfg), [])

    def test_a_null_agents_value_yields_empty(self):
        payload = json.dumps({"result": {"agents": None}})
        with mock.patch.object(hw.subprocess, "run", return_value=completed(payload)):
            self.assertEqual(hw.fetch_agents(self.cfg), [])

    def test_a_non_list_agents_value_yields_empty(self):
        payload = json.dumps({"result": {"agents": {"pane_id": "w1:p1"}}})
        with mock.patch.object(hw.subprocess, "run", return_value=completed(payload)):
            self.assertEqual(hw.fetch_agents(self.cfg), [])

    def test_unparseable_output_yields_empty(self):
        with mock.patch.object(hw.subprocess, "run", return_value=completed("nope")):
            self.assertEqual(hw.fetch_agents(self.cfg), [])

    def test_a_timeout_yields_empty(self):
        error = hw.subprocess.TimeoutExpired(cmd="herdr", timeout=3)
        with mock.patch.object(hw.subprocess, "run", side_effect=error):
            self.assertEqual(hw.fetch_agents(self.cfg), [])

    def test_a_missing_binary_yields_empty(self):
        with mock.patch.object(hw.subprocess, "run", side_effect=FileNotFoundError()):
            self.assertEqual(hw.fetch_agents(self.cfg), [])

    def test_the_invocation_is_agent_list_with_a_three_second_timeout(self):
        with mock.patch.object(hw.subprocess, "run",
                               return_value=completed("{}")) as run:
            hw.fetch_agents(self.cfg)
        self.assertEqual(run.call_args.args[0], ["/opt/herdr", "agent", "list"])
        self.assertEqual(run.call_args.kwargs["timeout"], 3)


class TestBinaryResolution(unittest.TestCase):
    def test_the_config_value_wins(self):
        self.assertEqual(hw.herdr_bin({"herdr_bin": "/from/config"}), "/from/config")

    def test_it_falls_back_to_a_path_lookup(self):
        with mock.patch.object(hw.shutil, "which", return_value="/from/path"):
            self.assertEqual(hw.herdr_bin({"herdr_bin": None}), "/from/path")

    def test_it_falls_back_to_local_bin(self):
        with mock.patch.object(hw.shutil, "which", return_value=None):
            self.assertEqual(hw.herdr_bin({}),
                             os.path.expanduser("~/.local/bin/herdr"))


SESSIONS = {"sessions": [{"name": "default", "running": True},
                         {"name": "work", "running": True},
                         {"name": "old", "running": False}]}


def router(responses):
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        value = responses.get(tuple(argv[1:]))
        if isinstance(value, BaseException):
            raise value
        return completed(json.dumps(value) if value is not None else "")

    return run, calls


def agents_payload(*panes):
    return {"result": {"agents": [{"pane_id": pane} for pane in panes]}}


class TestSessionDiscovery(unittest.TestCase):
    def setUp(self):
        hw._WARNED.clear()
        self.cfg = {"herdr_bin": "/opt/herdr", "sessions": None}

    def test_running_sessions_are_returned_in_order(self):
        run, calls = router({("session", "list", "--json"): SESSIONS})
        with mock.patch.object(hw.subprocess, "run", side_effect=run):
            self.assertEqual(hw.list_sessions(self.cfg), ["default", "work"])
        self.assertEqual(calls, [["/opt/herdr", "session", "list", "--json"]])

    def test_the_sessions_key_filters_without_reordering(self):
        self.cfg["sessions"] = ["work", "old", "missing", "default"]
        run, _ = router({("session", "list", "--json"): SESSIONS})
        with mock.patch.object(hw.subprocess, "run", side_effect=run):
            self.assertEqual(hw.list_sessions(self.cfg), ["default", "work"])

    def test_a_truthy_non_boolean_running_value_is_not_running(self):
        payload = {"sessions": [{"name": "default", "running": "yes"}]}
        run, _ = router({("session", "list", "--json"): payload})
        with mock.patch.object(hw.subprocess, "run", side_effect=run):
            self.assertEqual(hw.list_sessions(self.cfg), [])

    def test_a_failing_session_list_returns_none(self):
        run, _ = router({("session", "list", "--json"): FileNotFoundError()})
        with mock.patch.object(hw.subprocess, "run", side_effect=run):
            self.assertIsNone(hw.list_sessions(self.cfg))

    def test_output_without_a_sessions_array_returns_none(self):
        run, _ = router({("session", "list", "--json"): {"result": {}}})
        with mock.patch.object(hw.subprocess, "run", side_effect=run):
            self.assertIsNone(hw.list_sessions(self.cfg))


class TestSessionAgents(unittest.TestCase):
    def setUp(self):
        hw._WARNED.clear()
        self.cfg = {"herdr_bin": "/opt/herdr", "sessions": None}

    def test_agents_from_every_running_session_are_tagged(self):
        run, calls = router({
            ("session", "list", "--json"): SESSIONS,
            ("--session", "default", "agent", "list"): agents_payload("w1:p1"),
            ("--session", "work", "agent", "list"): agents_payload("w1:p1"),
        })
        with mock.patch.object(hw.subprocess, "run", side_effect=run):
            agents = hw.fetch_agents(self.cfg)
        self.assertEqual(agents, [{"pane_id": "w1:p1", "session": "default"},
                                  {"pane_id": "w1:p1", "session": "work"}])
        self.assertNotIn(["/opt/herdr", "--session", "old", "agent", "list"], calls)

    def test_a_failing_session_is_skipped(self):
        run, _ = router({
            ("session", "list", "--json"): SESSIONS,
            ("--session", "default", "agent", "list"): agents_payload("w1:p1"),
            ("--session", "work", "agent", "list"):
                hw.subprocess.TimeoutExpired(cmd="herdr", timeout=3),
        })
        with mock.patch.object(hw.subprocess, "run", side_effect=run):
            agents = hw.fetch_agents(self.cfg)
        self.assertEqual(agents, [{"pane_id": "w1:p1", "session": "default"}])

    def test_failed_discovery_falls_back_to_the_unscoped_list(self):
        run, calls = router({
            ("session", "list", "--json"): FileNotFoundError(),
            ("agent", "list"): agents_payload("w1:p1"),
        })
        with mock.patch.object(hw.subprocess, "run", side_effect=run):
            agents = hw.fetch_agents(self.cfg)
        self.assertEqual(agents, [{"pane_id": "w1:p1"}])
        self.assertEqual(calls[-1], ["/opt/herdr", "agent", "list"])

    def test_no_running_session_yields_empty_without_an_agent_query(self):
        run, calls = router({("session", "list", "--json"): {"sessions": []}})
        with mock.patch.object(hw.subprocess, "run", side_effect=run):
            self.assertEqual(hw.fetch_agents(self.cfg), [])
        self.assertEqual(len(calls), 1)

    def test_known_sessions_skip_discovery(self):
        run, calls = router({
            ("--session", "work", "agent", "list"): agents_payload("w1:p1"),
        })
        with mock.patch.object(hw.subprocess, "run", side_effect=run):
            agents = hw.fetch_agents(self.cfg, ["work"])
        self.assertEqual(agents, [{"pane_id": "w1:p1", "session": "work"}])
        self.assertEqual(calls, [["/opt/herdr", "--session", "work", "agent", "list"]])

    def test_non_object_agents_are_dropped_when_tagging(self):
        run, _ = router({
            ("--session", "work", "agent", "list"):
                {"result": {"agents": ["junk", {"pane_id": "w1:p1"}]}},
        })
        with mock.patch.object(hw.subprocess, "run", side_effect=run):
            agents = hw.fetch_agents(self.cfg, ["work"])
        self.assertEqual(agents, [{"pane_id": "w1:p1", "session": "work"}])

    def test_herdr_argv_scopes_only_when_a_session_is_given(self):
        self.assertEqual(hw.herdr_argv(self.cfg, "work", "agent", "list"),
                         ["/opt/herdr", "--session", "work", "agent", "list"])
        self.assertEqual(hw.herdr_argv(self.cfg, None, "agent", "list"),
                         ["/opt/herdr", "agent", "list"])


if __name__ == "__main__":
    unittest.main()
