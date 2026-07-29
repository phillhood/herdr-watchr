import json
import pathlib
import unittest

import support  # noqa: F401
import wire

EXAMPLES = pathlib.Path(support.ROOT) / "waybar" / "examples"


def _strip(text):
    out = []
    i = 0
    while i < len(text):
        if wire._is_comment(text, i):
            i = wire._end_of_comment(text, i)
            continue
        if text[i] == '"':
            j = wire._end_of_string(text, i)
            out.append(text[i:j])
            i = j
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


PRETTY = '''{
  "modules-center": [
    "clock"
  ],
  "clock": {"format": "{:%H:%M}"}
}
'''

SINGLE_LINE = '{"modules-center": ["clock"], "clock": {}}'

EMPTY_LIST = '{"modules-center": [], "clock": {}}'

WITH_COMMENT = '''{
  // "modules-center": ["decoy"]
  "modules-center": ["clock"],
  "group/x": {"modules": ["a"]}
}
'''

INCLUDE_ARRAY = '{"include": ["/a.jsonc"], "modules-center": ["clock"]}'

INCLUDE_STRING = '{"include": "/a.jsonc", "modules-center": ["clock"]}'

CORPUS = (PRETTY, SINGLE_LINE, EMPTY_LIST, WITH_COMMENT, INCLUDE_ARRAY)


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


class TestConfigSplice(unittest.TestCase):
    def install(self, text, position="center"):
        return wire.config_install(text, "/w/herdr-watchr.jsonc", position)

    def test_the_group_lands_in_the_named_list(self):
        out = self.install(PRETTY)
        arr = wire.value_offset(out, "modules-center")
        close = wire.matching_bracket(out, arr)
        self.assertIn(wire.GROUP, out[arr:close])

    def test_the_include_is_added_when_absent(self):
        out = self.install(PRETTY)
        self.assertEqual(
            json.loads(_strip(out))["include"], ["/w/herdr-watchr.jsonc"])

    def test_it_appends_to_an_existing_include_array(self):
        out = self.install(INCLUDE_ARRAY)
        self.assertEqual(json.loads(_strip(out))["include"],
                         ["/w/herdr-watchr.jsonc", "/a.jsonc"])

    def test_an_include_string_is_refused(self):
        with self.assertRaises(wire.ScanError):
            self.install(INCLUDE_STRING)

    def test_a_missing_position_key_is_refused(self):
        with self.assertRaises(wire.ScanError):
            self.install(PRETTY, "left")

    def test_an_unknown_position_is_refused(self):
        with self.assertRaises(wire.ScanError):
            self.install(PRETTY, "sideways")

    def test_the_decoy_in_a_comment_is_not_touched(self):
        out = self.install(WITH_COMMENT)
        self.assertIn('// "modules-center": ["decoy"]', out)

    def test_a_nested_modules_key_is_not_touched(self):
        out = self.install(WITH_COMMENT)
        self.assertIn('"group/x": {"modules": ["a"]}', out)

    def test_every_corpus_entry_stays_parseable(self):
        for text in CORPUS:
            out = self.install(text)
            parsed = json.loads(_strip(out))
            self.assertIn(wire.GROUP, parsed["modules-center"])

    def test_uninstall_restores_every_corpus_entry_byte_for_byte(self):
        for text in CORPUS:
            self.assertEqual(wire.config_uninstall(self.install(text)), text)

    def test_installing_twice_is_the_same_as_once(self):
        for text in CORPUS:
            once = self.install(text)
            self.assertEqual(self.install(once), once)

    def test_changing_position_moves_the_entry(self):
        text = '{"modules-left": [], "modules-center": ["clock"]}'
        out = wire.config_install(
            wire.config_install(text, "/w/h.jsonc", "center"),
            "/w/h.jsonc", "left")
        parsed = json.loads(_strip(out))
        self.assertIn(wire.GROUP, parsed["modules-left"])
        self.assertNotIn(wire.GROUP, parsed["modules-center"])


class TestManualInstallDetection(unittest.TestCase):
    def test_a_hand_wired_config_is_detected(self):
        self.assertTrue(wire.manual_install_present(
            '{"modules-center": ["group/herdr-watchr"]}'))

    def test_our_own_output_is_not_detected(self):
        out = wire.config_install(PRETTY, "/w/h.jsonc", "center")
        self.assertFalse(wire.manual_install_present(out))

    def test_an_unrelated_config_is_not_detected(self):
        self.assertFalse(wire.manual_install_present(PRETTY))


if __name__ == "__main__":
    unittest.main()
