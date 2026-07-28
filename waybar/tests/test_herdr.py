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


if __name__ == "__main__":
    unittest.main()
