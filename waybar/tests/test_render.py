import contextlib
import io
import json
import unittest

import support

hw = support.load_script()
MISSING = {"HERDR_WATCHR_CONFIG": "/nonexistent/herdr-watchr/config.json"}


def agent(status, ws="w1", title="task", pane="w1:p1", tid="t1", session=None):
    out = {"agent_status": status, "workspace_id": ws, "pane_id": pane,
           "terminal_id": tid, "terminal_title_stripped": title}
    if session is not None:
        out["session"] = session
    return out


class RenderCase(unittest.TestCase):
    def setUp(self):
        hw._WARNED.clear()
        self.cfg = hw.load_config(env=MISSING)


class TestStatusOutput(RenderCase):
    def test_text_is_a_colored_glyph_and_a_count(self):
        agents = [agent("working", pane="w5:p1"), agent("working", pane="w5:p9")]
        out = hw.status_output("working", agents, self.cfg)
        self.assertEqual(out["text"],
                         "<span color='#8b6fd4'>\U000F06A9</span> 2")
        self.assertEqual(out["class"], ["herdr-watchr", "working"])

    def test_only_matching_agents_are_counted(self):
        agents = [agent("working", pane="w5:p1"), agent("blocked", pane="w6:p1")]
        self.assertEqual(hw.status_output("working", agents, self.cfg)["text"][-1],
                         "1")

    def test_an_empty_status_renders_nothing(self):
        out = hw.status_output("done", [agent("working")], self.cfg)
        self.assertEqual(out["text"], "")
        self.assertEqual(out["tooltip"], "")
        self.assertEqual(out["class"], ["herdr-watchr", "done", "empty"])

    def test_an_unknown_status_name_renders_nothing(self):
        self.assertEqual(hw.status_output("bogus", [agent("idle")], self.cfg)["text"],
                         "")

    def test_the_tooltip_lists_agents_in_contract_order(self):
        agents = [agent("idle", ws="w8", title="b", pane="w8:p1"),
                  agent("idle", ws="w5", title="a", pane="w5:p1")]
        self.assertEqual(hw.status_output("idle", agents, self.cfg)["tooltip"],
                         "w5  a\nw8  b")

    def test_the_configured_color_is_used(self):
        cfg = hw.deep_merge(self.cfg, {"colors": {"blocked": "#ed8796"}})
        out = hw.status_output("blocked", [agent("blocked")], cfg)
        self.assertIn("#ed8796", out["text"])

    def test_the_tooltip_names_sessions_when_agents_span_several(self):
        agents = [agent("idle", ws="w1", title="b", pane="w1:p1", session="work"),
                  agent("idle", ws="w5", title="a", pane="w5:p1", session="default")]
        self.assertEqual(hw.status_output("idle", agents, self.cfg)["tooltip"],
                         "default  w5  a\nwork  w1  b")

    def test_the_prefix_follows_every_fetched_agent_not_just_the_group(self):
        agents = [agent("idle", ws="w5", title="a", pane="w5:p1", session="default"),
                  agent("blocked", pane="w1:p1", session="work")]
        self.assertEqual(hw.status_output("idle", agents, self.cfg)["tooltip"],
                         "default  w5  a")

    def test_a_single_session_gets_no_prefix(self):
        agents = [agent("idle", ws="w5", title="a", pane="w5:p1", session="work")]
        self.assertEqual(hw.status_output("idle", agents, self.cfg)["tooltip"],
                         "w5  a")


class TestAgentLine(RenderCase):
    def test_pango_markup_is_escaped(self):
        line = hw.agent_line(agent("idle", ws="w5", title="a & b <x>"))
        self.assertEqual(line, "w5  a &amp; b &lt;x&gt;")

    def test_a_missing_workspace_shows_a_placeholder(self):
        self.assertEqual(hw.agent_line({"terminal_title_stripped": "x"}), "?  x")

    def test_a_null_title_renders_empty(self):
        self.assertEqual(hw.agent_line({"workspace_id": "w1",
                                        "terminal_title_stripped": None}),
                         "w1  ")

    def test_surrounding_whitespace_is_stripped_from_the_title(self):
        self.assertEqual(hw.agent_line({"workspace_id": "w1",
                                        "terminal_title_stripped": "  x  "}),
                         "w1  x")

    def test_the_session_prefix_is_escaped(self):
        line = hw.agent_line(agent("idle", ws="w5", title="x", session="a<b"),
                             show_session=True)
        self.assertEqual(line, "a&lt;b  w5  x")


class TestStateSignature(RenderCase):
    def test_it_changes_when_a_status_changes(self):
        urgency = self.cfg["urgency"]
        self.assertNotEqual(
            hw.state_signature([agent("working", pane="w5:p1")], urgency),
            hw.state_signature([agent("blocked", pane="w5:p1")], urgency))

    def test_it_is_independent_of_array_order(self):
        urgency = self.cfg["urgency"]
        x = agent("working", pane="w5:p1")
        y = agent("idle", pane="w6:p1")
        self.assertEqual(hw.state_signature([x, y], urgency),
                         hw.state_signature([y, x], urgency))

    def test_it_changes_when_an_agent_appears(self):
        urgency = self.cfg["urgency"]
        one = [agent("idle", pane="w1:p1")]
        two = one + [agent("idle", pane="w2:p1")]
        self.assertNotEqual(hw.state_signature(one, urgency),
                            hw.state_signature(two, urgency))

    def test_it_ignores_a_title_change(self):
        urgency = self.cfg["urgency"]
        self.assertEqual(
            hw.state_signature([agent("idle", pane="w1:p1", title="a")], urgency),
            hw.state_signature([agent("idle", pane="w1:p1", title="b")], urgency))

    def test_the_same_pane_in_two_sessions_is_two_agents(self):
        urgency = self.cfg["urgency"]
        one = [agent("idle", pane="w1:p1", session="default")]
        two = one + [agent("idle", pane="w1:p1", session="work")]
        self.assertNotEqual(hw.state_signature(one, urgency),
                            hw.state_signature(two, urgency))

    def test_it_changes_when_an_agent_moves_session(self):
        urgency = self.cfg["urgency"]
        self.assertNotEqual(
            hw.state_signature([agent("idle", session="default")], urgency),
            hw.state_signature([agent("idle", session="work")], urgency))


class TestEmit(RenderCase):
    def test_it_writes_one_json_line(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            hw.emit({"text": "x"})
        self.assertEqual(json.loads(out.getvalue()), {"text": "x"})
        self.assertTrue(out.getvalue().endswith("\n"))


if __name__ == "__main__":
    unittest.main()
