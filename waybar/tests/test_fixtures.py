import unittest

import support

REQUIRED_TOP = {"name", "agents", "expected"}
REQUIRED_EXPECTED = {"order", "counts", "agents", "first_target", "cycle_target"}
VOCABULARY = {"blocked", "idle", "done", "working", "unknown"}


class TestFixtureShape(unittest.TestCase):
    def setUp(self):
        self.fixtures = support.load_fixtures()

    def test_the_directory_covers_every_required_case(self):
        self.assertGreaterEqual(len(self.fixtures), 11)

    def test_every_fixture_has_the_required_keys(self):
        for path, data in self.fixtures:
            with self.subTest(fixture=path.name):
                self.assertTrue(REQUIRED_TOP.issubset(data))
                self.assertTrue(REQUIRED_EXPECTED.issubset(data["expected"]))

    def test_no_fixture_has_an_unknown_expected_key(self):
        for path, data in self.fixtures:
            with self.subTest(fixture=path.name):
                self.assertTrue(set(data["expected"]).issubset(REQUIRED_EXPECTED))

    def test_order_counts_and_agents_name_the_same_statuses(self):
        for path, data in self.fixtures:
            expected = data["expected"]
            with self.subTest(fixture=path.name):
                self.assertEqual(sorted(expected["counts"]), sorted(expected["order"]))
                self.assertEqual(sorted(expected["agents"]), sorted(expected["order"]))

    def test_every_expected_group_is_sorted_and_counted(self):
        for path, data in self.fixtures:
            expected = data["expected"]
            for name, panes in expected["agents"].items():
                with self.subTest(fixture=path.name, status=name):
                    self.assertEqual(len(panes), expected["counts"][name])
                    self.assertEqual(panes, sorted(panes))

    def test_every_expected_status_is_in_the_vocabulary(self):
        for path, data in self.fixtures:
            with self.subTest(fixture=path.name):
                self.assertTrue(set(data["expected"]["order"]).issubset(VOCABULARY))

    def test_every_agent_declares_a_pane_id(self):
        for path, data in self.fixtures:
            with self.subTest(fixture=path.name):
                self.assertTrue(all("pane_id" in a for a in data["agents"]))

    def test_every_target_names_a_pane_in_its_own_group(self):
        for path, data in self.fixtures:
            expected = data["expected"]
            for key in ("first_target", "cycle_target"):
                target = expected.get(key)
                if not target:
                    continue
                panes = expected["agents"].get(target["status"], [])
                with self.subTest(fixture=path.name, target=key):
                    self.assertIn(target["status"], VOCABULARY)
                    if target["expect"] is None:
                        self.assertEqual(panes, [])
                    else:
                        self.assertIn(target["expect"], panes)


if __name__ == "__main__":
    unittest.main()
