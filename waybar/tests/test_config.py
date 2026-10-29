import json
import os
import tempfile
import unittest

import support

hw = support.load_script()
MISSING = {"HERDR_WATCHR_CONFIG": "/nonexistent/herdr-watchr/config.json"}


class ConfigCase(unittest.TestCase):
    def setUp(self):
        hw._WARNED.clear()

    def with_config(self, data):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = os.path.join(directory.name, "config.json")
        with open(path, "w", encoding="utf-8") as fh:
            if isinstance(data, str):
                fh.write(data)
            else:
                json.dump(data, fh)
        return {"HERDR_WATCHR_CONFIG": path}


class TestDeepMerge(ConfigCase):
    def test_a_partial_dict_merge_keeps_siblings(self):
        got = hw.deep_merge({"colors": {"blocked": "#000", "idle": "#111"}},
                            {"colors": {"blocked": "#f00"}})
        self.assertEqual(got, {"colors": {"blocked": "#f00", "idle": "#111"}})

    def test_a_scalar_overrides_a_scalar(self):
        self.assertEqual(hw.deep_merge({"poll_seconds": 1.5}, {"poll_seconds": 5}),
                         {"poll_seconds": 5})

    def test_a_scalar_replaces_a_dict(self):
        self.assertEqual(hw.deep_merge({"a": {"b": 1}}, {"a": 2}), {"a": 2})

    def test_the_base_is_not_mutated(self):
        base = {"colors": {"blocked": "#000"}}
        hw.deep_merge(base, {"colors": {"blocked": "#f00"}})
        self.assertEqual(base, {"colors": {"blocked": "#000"}})

    def test_a_null_override_is_a_no_op(self):
        self.assertEqual(hw.deep_merge({"a": 1}, None), {"a": 1})

    def test_a_non_dict_override_is_ignored(self):
        self.assertEqual(hw.deep_merge({"a": 1}, "oops"), {"a": 1})
        self.assertEqual(hw.deep_merge({"a": 1}, ["b"]), {"a": 1})

    def test_the_result_does_not_alias_nested_dicts_from_the_base(self):
        base = {"colors": {"blocked": "#000"}}
        merged = hw.deep_merge(base, {})
        merged["colors"]["blocked"] = "#fff"
        self.assertEqual(base["colors"]["blocked"], "#000")


class TestResolution(ConfigCase):
    def test_sessions_default_to_every_running_session(self):
        self.assertIsNone(hw.load_config(env=MISSING)["sessions"])

    def test_the_host_section_can_override_sessions(self):
        env = self.with_config({"sessions": ["default"],
                                "waybar": {"sessions": ["work"]}})
        self.assertEqual(hw.load_config(env=env)["sessions"], ["work"])

    def test_defaults_apply_when_there_is_no_file(self):
        cfg = hw.load_config(env=MISSING)
        self.assertEqual(cfg["colors"]["blocked"], "#d64545")
        self.assertEqual(cfg["signal"], 8)
        self.assertEqual(cfg["click_action"], "first")
        self.assertEqual(cfg["poll_seconds"], 1.5)

    def test_a_file_value_overrides_a_default_and_leaves_siblings(self):
        cfg = hw.load_config(env=self.with_config({"colors": {"blocked": "#ff0000"}}))
        self.assertEqual(cfg["colors"]["blocked"], "#ff0000")
        self.assertEqual(cfg["colors"]["idle"], "#4caf7d")

    def test_the_host_section_beats_the_shared_trunk(self):
        env = self.with_config({"colors": {"blocked": "#111111"},
                                "waybar": {"colors": {"blocked": "#222222"}}})
        self.assertEqual(hw.load_config(env=env)["colors"]["blocked"], "#222222")

    def test_the_other_host_section_does_not_leak(self):
        cfg = hw.load_config(env=self.with_config({"macos": {"show_when_empty": False}}))
        self.assertNotIn("show_when_empty", cfg)
        self.assertNotIn("macos", cfg)
        self.assertNotIn("waybar", cfg)

    def test_the_macos_host_resolves_its_own_section(self):
        cfg = hw.load_config(env=MISSING, host="macos")
        self.assertEqual(cfg["icons"]["blocked"], "bell.fill")
        self.assertTrue(cfg["show_when_empty"])

    def test_an_invalid_urgency_list_falls_back_to_the_default_order(self):
        cfg = hw.load_config(env=self.with_config({"urgency": ["blocked", "idle"]}))
        self.assertEqual(cfg["urgency"], list(hw.VOCABULARY))

    def test_a_valid_urgency_permutation_is_kept(self):
        order = ["working", "blocked", "done", "idle", "unknown"]
        cfg = hw.load_config(env=self.with_config({"urgency": order}))
        self.assertEqual(cfg["urgency"], order)

    def test_the_default_path_respects_xdg_config_home(self):
        self.assertEqual(hw.config_path({"XDG_CONFIG_HOME": "/x"}),
                         "/x/herdr-watchr/config.json")

    def test_the_default_path_falls_back_to_dot_config(self):
        self.assertEqual(hw.config_path({}),
                         os.path.expanduser("~/.config/herdr-watchr/config.json"))


class TestEnvOverrides(ConfigCase):
    def test_env_beats_file(self):
        env = self.with_config({"poll_seconds": 9.0, "waybar": {"signal": 3}})
        env["HERDR_WATCHR_POLL"] = "0.25"
        env["HERDR_WATCHR_SIGNAL"] = "5"
        cfg = hw.load_config(env=env)
        self.assertEqual(cfg["poll_seconds"], 0.25)
        self.assertEqual(cfg["signal"], 5)

    def test_the_watchr_prefix_beats_the_legacy_bin_variable(self):
        env = self.with_config({"herdr_bin": "/from/file"})
        env["HERDR_BIN"] = "/from/legacy"
        env["HERDR_WATCHR_BIN"] = "/from/watchr"
        self.assertEqual(hw.load_config(env=env)["herdr_bin"], "/from/watchr")

    def test_the_legacy_bin_variable_is_accepted_as_a_fallback(self):
        env = self.with_config({"herdr_bin": "/from/file"})
        env["HERDR_BIN"] = "/from/legacy"
        self.assertEqual(hw.load_config(env=env)["herdr_bin"], "/from/legacy")

    def test_a_non_numeric_poll_falls_back_to_the_file_value(self):
        env = self.with_config({"poll_seconds": 9.0})
        env["HERDR_WATCHR_POLL"] = "soon"
        self.assertEqual(hw.load_config(env=env)["poll_seconds"], 9.0)

    def test_a_non_numeric_signal_falls_back_to_the_file_value(self):
        env = self.with_config({"waybar": {"signal": 3}})
        env["HERDR_WATCHR_SIGNAL"] = "loud"
        self.assertEqual(hw.load_config(env=env)["signal"], 3)


class TestMalformedInput(ConfigCase):
    def test_unparseable_json_falls_back_to_defaults(self):
        cfg = hw.load_config(env=self.with_config("{not json"))
        self.assertEqual(cfg["colors"]["blocked"], "#d64545")

    def test_a_non_object_top_level_falls_back_to_defaults(self):
        self.assertEqual(hw.load_config(env=self.with_config(["nope"]))["signal"], 8)

    def test_a_malformed_file_warns_exactly_once(self):
        env = self.with_config("{not json")
        hw.load_config(env=env)
        hw.load_config(env=env)
        self.assertEqual(len(hw._WARNED), 1)

    def test_a_non_dict_host_section_falls_back_to_defaults(self):
        cfg = hw.load_config(env=self.with_config({"waybar": "oops"}))
        self.assertEqual(cfg["signal"], 8)
        self.assertEqual(cfg["click_action"], "first")

    def test_a_non_dict_host_section_warns(self):
        hw.load_config(env=self.with_config({"waybar": "oops"}))
        self.assertEqual(len(hw._WARNED), 1)

    def test_a_resolved_config_does_not_alias_module_defaults(self):
        cfg = hw.load_config(env=MISSING)
        self.assertIsNot(cfg["colors"], hw.DEFAULTS["colors"])
        cfg["colors"]["blocked"] = "CORRUPTED"
        self.assertEqual(hw.DEFAULTS["colors"]["blocked"], "#d64545")
        self.assertEqual(hw.load_config(env=MISSING)["colors"]["blocked"], "#d64545")


class TestPollInterval(ConfigCase):
    def test_a_valid_value_passes_through(self):
        self.assertEqual(hw.poll_interval({"poll_seconds": 2.5}), 2.5)

    def test_a_non_numeric_value_falls_back(self):
        self.assertEqual(hw.poll_interval({"poll_seconds": "fast"}), 1.5)

    def test_a_missing_value_falls_back(self):
        self.assertEqual(hw.poll_interval({}), 1.5)

    def test_a_zero_value_is_clamped(self):
        self.assertEqual(hw.poll_interval({"poll_seconds": 0}), 0.1)


class TestSchemaAgreesWithDefaults(ConfigCase):
    def test_the_schema_defaults_are_the_script_defaults(self):
        self.assertEqual(support.schema_defaults(support.load_schema()), hw.DEFAULTS)


class TestSchemaPermitsHostSectionOverrides(ConfigCase):
    def test_shared_keys_are_permitted_in_both_host_sections(self):
        schema = support.load_schema()
        for section in ("waybar", "macos"):
            properties = schema["properties"][section]["properties"]
            with self.subTest(section=section):
                self.assertIn("colors", properties)
                self.assertIn("urgency", properties)
                self.assertIn("poll_seconds", properties)
                self.assertIn("herdr_bin", properties)
                self.assertIn("sessions", properties)
                self.assertFalse(schema["properties"][section]["additionalProperties"])


if __name__ == "__main__":
    unittest.main()
