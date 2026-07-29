import json
import pathlib
import re
import shutil
import tempfile
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
    return re.sub(r",(\s*[\]}])", r"\1", "".join(out))


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

TRAILING_COMMA = '{"modules-center": ["clock",], "clock": {}}'

TRAILING_COMMA_INCLUDE = '{"include": ["/a.jsonc",], "modules-center": ["clock"]}'

CRLF = '{\r\n  "modules-center": ["clock"],\r\n  "clock": {}\r\n}\r\n'

TABS = '{\n\t"modules-center": [\n\t\t"clock"\n\t],\n\t"clock": {}\n}\n'

UNICODE = '{"modules-center": ["clock"], "clock": {"format": "☺ é"}}'

DUPLICATE_MODULES = '{"modules-center": ["a"], "modules-center": ["b"]}'

DUPLICATE_INCLUDE = ('{"include": ["/a.jsonc"], "include": ["/b.jsonc"], '
                     '"modules-center": ["clock"]}')

CORPUS = (PRETTY, SINGLE_LINE, EMPTY_LIST, WITH_COMMENT, INCLUDE_ARRAY,
          TRAILING_COMMA, TRAILING_COMMA_INCLUDE, CRLF, TABS, UNICODE)


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


class TestAdversarialShapes(unittest.TestCase):
    def install(self, text, position="center"):
        return wire.config_install(text, "/w/herdr-watchr.jsonc", position)

    def test_a_trailing_comma_does_not_become_a_double_comma(self):
        out = self.install(TRAILING_COMMA)
        self.assertNotIn(",,", out)
        self.assertIn(wire.GROUP, json.loads(_strip(out))["modules-center"])

    def test_a_trailing_comma_in_include_stays_valid(self):
        out = self.install(TRAILING_COMMA_INCLUDE)
        self.assertNotIn(",,", out)
        self.assertIn("/w/herdr-watchr.jsonc",
                      json.loads(_strip(out))["include"])

    def test_crlf_line_endings_survive_the_splice(self):
        out = self.install(CRLF)
        self.assertNotIn("\n", out.replace("\r\n", ""))

    def test_duplicate_modules_keys_are_refused(self):
        with self.assertRaises(wire.ScanError):
            self.install(DUPLICATE_MODULES)

    def test_duplicate_include_keys_are_refused(self):
        with self.assertRaises(wire.ScanError):
            self.install(DUPLICATE_INCLUDE)

    def test_a_marker_inside_a_string_before_the_splice_is_ignored(self):
        text = ('{"note": "%s", "modules-center": ["clock"]}' % wire.GRP_OPEN)
        out = self.install(text)
        self.assertEqual(wire.config_uninstall(out), text)

    def test_a_complete_marker_pair_inside_a_string_is_ignored(self):
        text = ('{"note": "%sx%s", "modules-center": ["clock"]}'
                % (wire.GRP_OPEN, wire.GRP_CLOSE))
        out = self.install(text)
        self.assertEqual(wire.config_uninstall(out), text)

    def test_an_include_marker_inside_a_string_is_ignored(self):
        text = ('{"note": "%s", "modules-center": ["clock"]}' % wire.MARK_OPEN)
        out = self.install(text)
        self.assertEqual(wire.config_uninstall(out), text)

    def test_comment_marks_ignores_string_contents(self):
        text = '{"a": "%s"}' % wire.GRP_OPEN
        self.assertEqual(wire.comment_marks(text, wire.GRP_OPEN), [])

    def test_comment_marks_finds_a_real_comment(self):
        text = '{%s"a": 1}' % wire.GRP_OPEN
        self.assertEqual(wire.comment_marks(text, wire.GRP_OPEN), [1])

    def test_a_string_marker_does_not_suppress_manual_detection(self):
        text = '{"note": "%s", "x": "group/herdr-watchr"}' % wire.GRP_OPEN
        self.assertTrue(wire.manual_install_present(text))

    def test_an_unmatched_open_marker_is_refused(self):
        text = '%s\n{"modules-center": ["clock"]}' % wire.MARK_OPEN
        with self.assertRaises(wire.ScanError):
            self.install(text)

    def test_an_unmatched_close_marker_is_refused(self):
        text = '%s\n{"modules-center": ["clock"]}' % wire.MARK_CLOSE
        with self.assertRaises(wire.ScanError):
            self.install(text)

    def test_a_duplicated_open_marker_is_refused(self):
        text = '%s%s\n{"modules-center": ["clock"]}' % (wire.GRP_OPEN, wire.GRP_OPEN)
        with self.assertRaises(wire.ScanError):
            self.install(text)

    def test_a_close_before_its_open_is_refused(self):
        text = '%s%s\n{"modules-center": ["clock"]}' % (wire.GRP_CLOSE, wire.GRP_OPEN)
        with self.assertRaises(wire.ScanError):
            self.install(text)

    def test_uninstall_refuses_a_damaged_marker_pair(self):
        text = '%s\n{"modules-center": ["clock"]}' % wire.GRP_OPEN
        with self.assertRaises(wire.ScanError):
            wire.config_uninstall(text)

    def test_value_offsets_finds_every_depth_one_match(self):
        self.assertEqual(len(wire.value_offsets(DUPLICATE_MODULES,
                                                "modules-center")), 2)

    def test_a_nested_duplicate_does_not_count(self):
        text = '{"g": {"modules-center": [1]}, "modules-center": ["a"]}'
        self.assertEqual(len(wire.value_offsets(text, "modules-center")), 1)


class TestManualInstallDetection(unittest.TestCase):
    def test_a_hand_wired_config_is_detected(self):
        self.assertTrue(wire.manual_install_present(
            '{"modules-center": ["group/herdr-watchr"]}'))

    def test_our_own_output_is_not_detected(self):
        out = wire.config_install(PRETTY, "/w/h.jsonc", "center")
        self.assertFalse(wire.manual_install_present(out))

    def test_an_unrelated_config_is_not_detected(self):
        self.assertFalse(wire.manual_install_present(PRETTY))


class WireFilesystemCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.cfg = pathlib.Path(self.dir) / "config.jsonc"
        self.css = pathlib.Path(self.dir) / "style.css"
        self.cfg.write_text(PRETTY, encoding="utf-8")
        self.css.write_text("#clock { color: red; }\n", encoding="utf-8")

    def owned(self, name):
        return pathlib.Path(self.dir) / name


class TestInstallOnDisk(WireFilesystemCase):
    def test_it_writes_both_owned_files(self):
        wire.install(self.dir, "/opt/bin/herdr-watchr", "center", "1")
        self.assertTrue(self.owned("herdr-watchr.jsonc").exists())
        self.assertTrue(self.owned("herdr-watchr.css").exists())

    def test_the_owned_css_matches_the_example(self):
        wire.install(self.dir, "/opt/bin/herdr-watchr", "center", "1")
        self.assertEqual(
            self.owned("herdr-watchr.css").read_text(encoding="utf-8"),
            (EXAMPLES / "style.css").read_text(encoding="utf-8"))

    def test_it_backs_up_before_changing(self):
        wire.install(self.dir, "/opt/bin/herdr-watchr", "center", "77")
        self.assertTrue(self.owned("config.jsonc.herdr-watchr-backup-77").exists())

    def test_a_no_op_rerun_writes_no_second_backup(self):
        wire.install(self.dir, "/opt/bin/herdr-watchr", "center", "1")
        wire.install(self.dir, "/opt/bin/herdr-watchr", "center", "2")
        self.assertFalse(self.owned("config.jsonc.herdr-watchr-backup-2").exists())

    def test_uninstall_restores_the_config_bytes(self):
        wire.install(self.dir, "/opt/bin/herdr-watchr", "center", "1")
        wire.uninstall(self.dir, "2")
        self.assertEqual(self.cfg.read_text(encoding="utf-8"), PRETTY)

    def test_uninstall_restores_the_stylesheet_bytes(self):
        original = self.css.read_text(encoding="utf-8")
        wire.install(self.dir, "/opt/bin/herdr-watchr", "center", "1")
        wire.uninstall(self.dir, "2")
        self.assertEqual(self.css.read_text(encoding="utf-8"), original)

    def test_uninstall_removes_the_owned_files(self):
        wire.install(self.dir, "/opt/bin/herdr-watchr", "center", "1")
        wire.uninstall(self.dir, "2")
        self.assertFalse(self.owned("herdr-watchr.jsonc").exists())
        self.assertFalse(self.owned("herdr-watchr.css").exists())

    def test_a_symlinked_config_stays_a_symlink(self):
        real = pathlib.Path(self.dir) / "real.jsonc"
        real.write_text(PRETTY, encoding="utf-8")
        self.cfg.unlink()
        self.cfg.symlink_to(real)
        wire.install(self.dir, "/opt/bin/herdr-watchr", "center", "1")
        self.assertTrue(self.cfg.is_symlink())
        self.assertIn(wire.GROUP, real.read_text(encoding="utf-8"))

    def test_a_manual_install_is_refused(self):
        self.cfg.write_text('{"modules-center": ["group/herdr-watchr"]}',
                            encoding="utf-8")
        with self.assertRaises(wire.ScanError):
            wire.install(self.dir, "/opt/bin/herdr-watchr", "center", "1")

    def test_force_overrides_the_manual_check(self):
        self.cfg.write_text('{"modules-center": ["group/herdr-watchr"]}',
                            encoding="utf-8")
        wire.install(self.dir, "/opt/bin/herdr-watchr", "center", "1", True)
        self.assertIn(wire.GRP_OPEN, self.cfg.read_text(encoding="utf-8"))

    def test_a_missing_config_is_refused(self):
        self.cfg.unlink()
        with self.assertRaises(wire.ScanError):
            wire.install(self.dir, "/opt/bin/herdr-watchr", "center", "1")

    def test_a_missing_stylesheet_is_refused(self):
        self.css.unlink()
        with self.assertRaises(wire.ScanError):
            wire.install(self.dir, "/opt/bin/herdr-watchr", "center", "1")

    def test_a_refusal_leaves_the_config_untouched(self):
        self.cfg.write_text(INCLUDE_STRING, encoding="utf-8")
        with self.assertRaises(wire.ScanError):
            wire.install(self.dir, "/opt/bin/herdr-watchr", "center", "1")
        self.assertEqual(self.cfg.read_text(encoding="utf-8"), INCLUDE_STRING)

    def test_a_refusal_leaves_the_stylesheet_untouched(self):
        original = self.css.read_text(encoding="utf-8")
        self.cfg.write_text(INCLUDE_STRING, encoding="utf-8")
        with self.assertRaises(wire.ScanError):
            wire.install(self.dir, "/opt/bin/herdr-watchr", "center", "1")
        self.assertEqual(self.css.read_text(encoding="utf-8"), original)

    def test_a_config_without_an_extension_is_found(self):
        self.cfg.unlink()
        plain = pathlib.Path(self.dir) / "config"
        plain.write_text(PRETTY, encoding="utf-8")
        wire.install(self.dir, "/opt/bin/herdr-watchr", "center", "1")
        self.assertIn(wire.GROUP, plain.read_text(encoding="utf-8"))


class TestRawByteRoundTrip(unittest.TestCase):
    def round_trip(self, config_bytes, css_bytes):
        directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, directory)
        cfg = pathlib.Path(directory) / "config.jsonc"
        css = pathlib.Path(directory) / "style.css"
        cfg.write_bytes(config_bytes)
        css.write_bytes(css_bytes)
        wire.install(directory, "/opt/bin/herdr-watchr", "center", "1")
        spliced = cfg.read_bytes()
        wire.uninstall(directory, "2")
        return spliced, cfg.read_bytes(), css.read_bytes()

    def test_crlf_config_and_css_restore_byte_for_byte(self):
        config_bytes = CRLF.encode("utf-8")
        css_bytes = b"#clock { color: red; }\r\n"
        _spliced, cfg_after, css_after = self.round_trip(config_bytes, css_bytes)
        self.assertEqual(cfg_after, config_bytes)
        self.assertEqual(css_after, css_bytes)

    def test_a_spliced_crlf_config_gains_no_bare_newline(self):
        config_bytes = CRLF.encode("utf-8")
        spliced, _cfg, _css = self.round_trip(config_bytes, b"#a{}\r\n")
        self.assertNotIn(b"\n", spliced.replace(b"\r\n", b""))

    def test_unicode_survives_byte_for_byte(self):
        config_bytes = UNICODE.encode("utf-8")
        _spliced, cfg_after, _css = self.round_trip(config_bytes, b"#a{}\n")
        self.assertEqual(cfg_after, config_bytes)

    def test_a_file_without_a_trailing_newline_restores(self):
        config_bytes = SINGLE_LINE.encode("utf-8")
        _spliced, cfg_after, _css = self.round_trip(config_bytes, b"#a{}")
        self.assertEqual(cfg_after, config_bytes)


class TestWireCli(WireFilesystemCase):
    def test_install_returns_zero(self):
        code = wire.main(["wire.py", "install", "--waybar-dir", self.dir,
                          "--binary", "/opt/bin/herdr-watchr", "--stamp", "1"])
        self.assertEqual(code, 0)

    def test_a_refusal_returns_one(self):
        self.cfg.unlink()
        code = wire.main(["wire.py", "install", "--waybar-dir", self.dir,
                          "--binary", "/opt/bin/herdr-watchr", "--stamp", "1"])
        self.assertEqual(code, 1)

    def test_an_unknown_action_returns_two(self):
        self.assertEqual(wire.main(["wire.py", "wat"]), 2)

    def test_an_unknown_option_returns_two(self):
        self.assertEqual(wire.main(["wire.py", "install", "--wat"]), 2)


if __name__ == "__main__":
    unittest.main()
