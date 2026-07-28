import unittest

import support

hw = support.load_script()
URGENCY = ["blocked", "idle", "done", "working", "unknown"]


class TestContractAgainstFixtures(unittest.TestCase):
    def setUp(self):
        self.fixtures = support.load_fixtures()

    def test_grouping_matches_every_fixture(self):
        for path, data in self.fixtures:
            groups = hw.group_agents(data["agents"], URGENCY)
            expected = data["expected"]
            with self.subTest(fixture=path.name):
                self.assertEqual(hw.status_order(groups, URGENCY), expected["order"])
                self.assertEqual({k: len(v) for k, v in groups.items() if v},
                                 expected["counts"])
                self.assertEqual(
                    {k: [a["pane_id"] for a in v] for k, v in groups.items() if v},
                    expected["agents"])

    def test_click_targets_match_every_fixture(self):
        for path, data in self.fixtures:
            groups = hw.group_agents(data["agents"], URGENCY)
            for key, action in (("first_target", "first"), ("cycle_target", "cycle")):
                target = data["expected"].get(key)
                if not target:
                    continue
                got = hw.select_target(groups.get(target["status"], []), action)
                with self.subTest(fixture=path.name, target=key):
                    self.assertEqual(got["pane_id"] if got else None,
                                     target["expect"])


class TestStatusMapping(unittest.TestCase):
    def test_an_unrecognised_status_maps_to_unknown(self):
        self.assertEqual(hw.status_of({"agent_status": "reticulating"}, URGENCY),
                         "unknown")

    def test_a_missing_status_maps_to_unknown(self):
        self.assertEqual(hw.status_of({}, URGENCY), "unknown")

    def test_a_null_status_maps_to_unknown(self):
        self.assertEqual(hw.status_of({"agent_status": None}, URGENCY), "unknown")

    def test_a_known_status_passes_through(self):
        self.assertEqual(hw.status_of({"agent_status": "working"}, URGENCY),
                         "working")


class TestOrdering(unittest.TestCase):
    def test_stable_sort_is_lexicographic_on_pane_id(self):
        agents = [{"pane_id": "w8:p1"}, {"pane_id": "w10:p1"}, {"pane_id": "w2:p1"}]
        self.assertEqual([a["pane_id"] for a in hw.stable_sort(agents)],
                         ["w10:p1", "w2:p1", "w8:p1"])

    def test_stable_sort_tolerates_a_missing_pane_id(self):
        agents = [{"pane_id": "w1:p1"}, {}]
        self.assertEqual([a.get("pane_id") for a in hw.stable_sort(agents)],
                         [None, "w1:p1"])

    def test_group_agents_keys_every_urgency_member(self):
        groups = hw.group_agents([], URGENCY)
        self.assertEqual(sorted(groups), sorted(URGENCY))

    def test_status_order_follows_the_configured_urgency(self):
        urgency = ["done", "blocked", "idle", "working", "unknown"]
        groups = hw.group_agents(
            [{"pane_id": "w1:p1", "agent_status": "blocked"},
             {"pane_id": "w2:p1", "agent_status": "done"}], urgency)
        self.assertEqual(hw.status_order(groups, urgency), ["done", "blocked"])


class TestSelectTarget(unittest.TestCase):
    def test_an_empty_group_selects_nothing(self):
        self.assertIsNone(hw.select_target([], "first"))
        self.assertIsNone(hw.select_target([], "cycle"))

    def test_an_unknown_click_action_behaves_as_first(self):
        group = [{"pane_id": "a", "focused": True}, {"pane_id": "b"}]
        self.assertEqual(hw.select_target(group, "nonsense")["pane_id"], "a")

    def test_a_null_click_action_behaves_as_first(self):
        group = [{"pane_id": "a", "focused": True}, {"pane_id": "b"}]
        self.assertEqual(hw.select_target(group, None)["pane_id"], "a")

    def test_a_string_focused_value_does_not_count_as_focused(self):
        group = [{"pane_id": "a", "focused": "yes"}, {"pane_id": "b"}]
        self.assertEqual(hw.select_target(group, "cycle")["pane_id"], "a")

    def test_an_integer_focused_value_does_not_count_as_focused(self):
        group = [{"pane_id": "a", "focused": 1}, {"pane_id": "b"}]
        self.assertEqual(hw.select_target(group, "cycle")["pane_id"], "a")


class TestNormalizeUrgency(unittest.TestCase):
    def test_a_permutation_is_accepted(self):
        value = ["done", "idle", "blocked", "unknown", "working"]
        self.assertEqual(hw.normalize_urgency(value), value)

    def test_a_short_list_is_rejected(self):
        self.assertEqual(hw.normalize_urgency(["blocked"]), URGENCY)

    def test_a_list_with_an_unknown_member_is_rejected(self):
        self.assertEqual(
            hw.normalize_urgency(["blocked", "idle", "done", "working", "wat"]),
            URGENCY)

    def test_a_non_list_is_rejected(self):
        self.assertEqual(hw.normalize_urgency("blocked"), URGENCY)
        self.assertEqual(hw.normalize_urgency(None), URGENCY)

    def test_a_mixed_type_list_is_rejected_without_raising(self):
        self.assertEqual(
            hw.normalize_urgency(["blocked", 1, "done", "working", "unknown"]),
            URGENCY)

    def test_a_list_with_an_unhashable_member_is_rejected_without_raising(self):
        self.assertEqual(
            hw.normalize_urgency(["blocked", ["x"], "done", "working", "unknown"]),
            URGENCY)


if __name__ == "__main__":
    unittest.main()
