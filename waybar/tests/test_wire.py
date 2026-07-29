import json
import pathlib
import unittest

import support  # noqa: F401
import wire

EXAMPLES = pathlib.Path(support.ROOT) / "waybar" / "examples"


class TestStringScan(unittest.TestCase):
    def test_it_returns_the_index_past_the_closing_quote(self):
        self.assertEqual(wire._end_of_string('"ab" x', 0), 4)

    def test_it_ignores_an_escaped_quote(self):
        self.assertEqual(wire._end_of_string('"a\\"b" x', 0), 6)

    def test_an_unterminated_string_raises(self):
        with self.assertRaises(wire.ScanError):
            wire._end_of_string('"abc', 0)


class TestCommentScan(unittest.TestCase):
    def test_a_line_comment_ends_at_the_newline(self):
        self.assertEqual(wire._end_of_comment("// x\ny", 0), 4)

    def test_a_block_comment_ends_after_the_terminator(self):
        self.assertEqual(wire._end_of_comment("/* x */y", 0), 7)

    def test_an_unterminated_block_comment_raises(self):
        with self.assertRaises(wire.ScanError):
            wire._end_of_comment("/* x", 0)


class TestTopLevelOpen(unittest.TestCase):
    def test_it_skips_leading_comments(self):
        self.assertEqual(wire.top_level_open("// hi\n  {}"), 8)

    def test_an_array_top_level_is_refused(self):
        with self.assertRaises(wire.ScanError):
            wire.top_level_open("[{}]")


class TestValueOffset(unittest.TestCase):
    def test_it_finds_a_depth_one_key(self):
        text = '{\n  "a": 1,\n  "modules-center": []\n}'
        self.assertEqual(wire.value_offset(text, "modules-center"),
                         text.index("[]"))

    def test_it_ignores_a_nested_key_of_the_same_name(self):
        text = '{\n  "g": {"modules": [1]},\n  "modules": []\n}'
        self.assertEqual(wire.value_offset(text, "modules"), text.index("[]"))

    def test_it_ignores_the_key_inside_a_comment(self):
        text = '{\n  // "modules-center": [1]\n  "modules-center": []\n}'
        self.assertEqual(wire.value_offset(text, "modules-center"),
                         text.index("[]"))

    def test_a_missing_key_returns_none(self):
        self.assertIsNone(wire.value_offset('{"a": 1}', "include"))


class TestMatchingBracket(unittest.TestCase):
    def test_it_skips_brackets_inside_strings(self):
        text = '["a]b", "c"]'
        self.assertEqual(wire.matching_bracket(text, 0), 11)

    def test_an_unbalanced_bracket_raises(self):
        with self.assertRaises(wire.ScanError):
            wire.matching_bracket("[1, 2", 0)


class TestLastContent(unittest.TestCase):
    def test_it_ignores_trailing_comments_and_space(self):
        text = '["a" /* z */ ]'
        stop = wire.matching_bracket(text, 0)
        self.assertEqual(wire._last_content(text, 1, stop), 3)

    def test_an_empty_array_has_no_content(self):
        self.assertEqual(wire._last_content("[  ]", 1, 3), -1)


class TestModuleConfig(unittest.TestCase):
    def test_it_matches_the_shipped_example(self):
        example = EXAMPLES / "waybar-config.jsonc"
        self.assertEqual(
            json.loads(wire.module_config("~/.local/bin/herdr-watchr")),
            json.loads(example.read_text(encoding="utf-8")))

    def test_the_binary_path_is_baked_into_every_command(self):
        generated = json.loads(wire.module_config("/opt/bin/herdr-watchr"))
        self.assertEqual(generated["custom/herdr-blocked"]["exec"],
                         "/opt/bin/herdr-watchr status blocked")
        self.assertEqual(generated["custom/herdr-blocked"]["on-click"],
                         "/opt/bin/herdr-watchr focus-status blocked")
        self.assertEqual(generated["custom/herdr-watchr-notify"]["exec"],
                         "/opt/bin/herdr-watchr notify")

    def test_the_vocabulary_matches_the_renderer(self):
        hw = support.load_script()
        self.assertEqual(tuple(wire.VOCABULARY), tuple(hw.VOCABULARY))


class TestCssSplice(unittest.TestCase):
    ORIGINAL = "#clock {\n  color: red;\n}\n"

    def test_the_import_lands_at_byte_zero(self):
        out = wire.css_install(self.ORIGINAL, "/w/herdr-watchr.css")
        self.assertTrue(out.startswith(wire.CSS_OPEN))
        self.assertIn('@import url("/w/herdr-watchr.css");', out)

    def test_the_original_rules_survive(self):
        out = wire.css_install(self.ORIGINAL, "/w/herdr-watchr.css")
        self.assertIn(self.ORIGINAL, out)

    def test_uninstall_restores_the_original_bytes(self):
        out = wire.css_install(self.ORIGINAL, "/w/herdr-watchr.css")
        self.assertEqual(wire.css_uninstall(out), self.ORIGINAL)

    def test_installing_twice_is_the_same_as_once(self):
        once = wire.css_install(self.ORIGINAL, "/w/herdr-watchr.css")
        twice = wire.css_install(once, "/w/herdr-watchr.css")
        self.assertEqual(once, twice)

    def test_uninstall_on_an_untouched_file_changes_nothing(self):
        self.assertEqual(wire.css_uninstall(self.ORIGINAL), self.ORIGINAL)


if __name__ == "__main__":
    unittest.main()
