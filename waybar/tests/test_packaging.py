import json
import os
import shutil
import subprocess
import tempfile
import unittest

import support

hw = support.load_script()
EXAMPLES = support.ROOT / "waybar" / "examples"


class TestInstallScript(unittest.TestCase):
    def install(self, *args):
        target = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, target)
        env = dict(os.environ, HERDR_WATCHR_PREFIX=target)
        proc = subprocess.run([str(support.ROOT / "waybar" / "install.sh")] + list(args),
                              capture_output=True, text=True, env=env, timeout=30)
        return target, proc

    def test_the_default_install_is_a_symlink_to_the_repo_script(self):
        target, proc = self.install()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        link = os.path.join(target, "herdr-watchr")
        self.assertTrue(os.path.islink(link))
        self.assertEqual(os.path.realpath(link), str(support.SCRIPT.resolve()))

    def test_copy_installs_an_executable_regular_file(self):
        target, proc = self.install("--copy")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        path = os.path.join(target, "herdr-watchr")
        self.assertFalse(os.path.islink(path))
        self.assertTrue(os.access(path, os.X_OK))

    def test_reinstalling_over_an_existing_link_succeeds(self):
        target = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, target)
        env = dict(os.environ, HERDR_WATCHR_PREFIX=target)
        script = str(support.ROOT / "waybar" / "install.sh")
        subprocess.run([script], capture_output=True, env=env, timeout=30)
        proc = subprocess.run([script], capture_output=True, text=True, env=env,
                              timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_an_unknown_option_exits_two(self):
        _target, proc = self.install("--wat")
        self.assertEqual(proc.returncode, 2)

    def test_a_target_off_path_is_reported(self):
        _target, proc = self.install()
        self.assertIn("not on PATH", proc.stderr)

    def test_the_printed_snippet_paths_exist(self):
        _target, proc = self.install()
        for line in proc.stdout.splitlines():
            for word in line.split():
                if word.startswith("/") and word.endswith((".jsonc", ".css")):
                    self.assertTrue(os.path.exists(word), word)


class TestExampleWaybarConfig(unittest.TestCase):
    def test_it_names_the_group_and_six_modules(self):
        text = (EXAMPLES / "waybar-config.jsonc").read_text(encoding="utf-8")
        self.assertIn('"group/herdr-watchr"', text)
        for status in hw.VOCABULARY:
            self.assertIn('"custom/herdr-%s"' % status, text)
        self.assertIn('"custom/herdr-watchr-notify"', text)

    def test_every_module_invokes_the_path_binary(self):
        text = (EXAMPLES / "waybar-config.jsonc").read_text(encoding="utf-8")
        self.assertNotIn("~/.config/waybar/herdr", text)
        self.assertEqual(text.count('"exec": "herdr-watchr status'), 5)
        self.assertEqual(text.count('"on-click": "herdr-watchr focus-status'), 5)


class TestExampleStylesheet(unittest.TestCase):
    def test_it_styles_the_group_and_its_children(self):
        text = (EXAMPLES / "style.css").read_text(encoding="utf-8")
        self.assertIn("#herdr-watchr {", text)
        self.assertIn("#herdr-watchr > widget", text)


class TestAuthorExampleConfig(unittest.TestCase):
    def setUp(self):
        hw._WARNED.clear()
        self.cfg = hw.load_config(
            env={"HERDR_WATCHR_CONFIG": str(EXAMPLES / "config.json")})

    def test_it_resolves_to_the_catppuccin_palette(self):
        self.assertEqual(self.cfg["colors"], {
            "blocked": "#ed8796", "idle": "#a6da95", "done": "#8bd5ca",
            "working": "#c6a0f6", "unknown": "#6e738d"})

    def test_it_selects_cycle_and_signal_eight(self):
        self.assertEqual(self.cfg["click_action"], "cycle")
        self.assertEqual(self.cfg["signal"], 8)

    def test_it_uses_the_hyprland_lua_focus_form(self):
        self.assertEqual(self.cfg["focus_window_cmd"],
                         ["hyprctl", "dispatch",
                          'hl.dsp.focus({window="address:{addr}"})'])

    def test_it_inherits_the_default_icons_rather_than_restating_them(self):
        raw = json.loads((EXAMPLES / "config.json").read_text(encoding="utf-8"))
        self.assertNotIn("icons", raw.get("waybar", {}))
        self.assertEqual(self.cfg["icons"], hw.DEFAULTS["waybar"]["icons"])


if __name__ == "__main__":
    unittest.main()
