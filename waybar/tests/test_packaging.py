import json
import os
import shutil
import subprocess
import tempfile
import unittest

import support

hw = support.load_script()
EXAMPLES = support.ROOT / "waybar" / "examples"


STOCK_CONFIG = '{"modules-center": ["clock"], "clock": {}}'
STOCK_CSS = "#clock { color: red; }\n"


class TestInstallScript(unittest.TestCase):
    def setUp(self):
        self.config_home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.config_home)
        self.waybar_dir = os.path.join(self.config_home, "waybar")
        os.makedirs(self.waybar_dir)
        self.write("config.jsonc", STOCK_CONFIG)
        self.write("style.css", STOCK_CSS)

    def write(self, name, text):
        with open(os.path.join(self.waybar_dir, name), "w") as fh:
            fh.write(text)

    def read(self, name):
        with open(os.path.join(self.waybar_dir, name)) as fh:
            return fh.read()

    def run_installer(self, target, *args):
        env = dict(os.environ, HERDR_WATCHR_PREFIX=target,
                   XDG_CONFIG_HOME=self.config_home)
        return subprocess.run(
            [str(support.ROOT / "waybar" / "install.sh")] + list(args),
            capture_output=True, text=True, env=env, timeout=30)

    def install(self, *args):
        target = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, target)
        return target, self.run_installer(target, *args)

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
        self.run_installer(target)
        proc = self.run_installer(target)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_an_unknown_option_exits_two(self):
        _target, proc = self.install("--wat")
        self.assertEqual(proc.returncode, 2)

    def test_a_target_off_path_is_reported(self):
        _target, proc = self.install()
        self.assertIn("not on PATH", proc.stderr)

    def test_it_wires_the_waybar_config(self):
        _target, proc = self.install()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        text = self.read("config.jsonc")
        self.assertIn("group/herdr-watchr", text)
        self.assertIn("herdr-watchr.jsonc", text)

    def test_it_imports_the_stylesheet(self):
        _target, proc = self.install()
        self.assertIn("herdr-watchr.css", self.read("style.css"))

    def test_it_writes_the_owned_files(self):
        self.install()
        self.assertTrue(os.path.exists(
            os.path.join(self.waybar_dir, "herdr-watchr.jsonc")))
        self.assertTrue(os.path.exists(
            os.path.join(self.waybar_dir, "herdr-watchr.css")))

    def test_the_owned_modules_use_the_installed_binary(self):
        target, _proc = self.install()
        modules = json.loads(self.read("herdr-watchr.jsonc"))
        self.assertEqual(modules["custom/herdr-blocked"]["exec"],
                         "%s/herdr-watchr status blocked" % target)

    def test_uninstall_restores_both_files(self):
        target, _proc = self.install()
        proc = self.run_installer(target, "--uninstall")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.read("config.jsonc"), STOCK_CONFIG)
        self.assertEqual(self.read("style.css"), STOCK_CSS)

    def test_uninstall_removes_the_installed_binary(self):
        target, _proc = self.install()
        self.run_installer(target, "--uninstall")
        self.assertFalse(os.path.exists(os.path.join(target, "herdr-watchr")))

    def test_uninstall_leaves_a_foreign_binary_alone(self):
        target, _proc = self.install()
        os.remove(os.path.join(target, "herdr-watchr"))
        with open(os.path.join(target, "herdr-watchr"), "w") as fh:
            fh.write("#!/bin/sh\necho not ours\n")
        self.run_installer(target, "--uninstall")
        self.assertTrue(os.path.exists(os.path.join(target, "herdr-watchr")))

    def test_a_foreign_binary_is_not_replaced(self):
        target = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, target)
        foreign = os.path.join(target, "herdr-watchr")
        with open(foreign, "w") as fh:
            fh.write("#!/bin/sh\necho not ours\n")
        proc = self.run_installer(target)
        self.assertEqual(proc.returncode, 1)
        with open(foreign) as fh:
            self.assertIn("not ours", fh.read())

    def test_a_foreign_binary_refusal_leaves_the_config_untouched(self):
        target = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, target)
        with open(os.path.join(target, "herdr-watchr"), "w") as fh:
            fh.write("#!/bin/sh\necho not ours\n")
        self.run_installer(target)
        self.assertEqual(self.read("config.jsonc"), STOCK_CONFIG)

    def test_force_replaces_a_foreign_binary(self):
        target = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, target)
        with open(os.path.join(target, "herdr-watchr"), "w") as fh:
            fh.write("#!/bin/sh\necho not ours\n")
        proc = self.run_installer(target, "--force")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(os.path.islink(os.path.join(target, "herdr-watchr")))

    def test_reinstalling_over_our_own_copy_is_allowed(self):
        target = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, target)
        self.run_installer(target, "--copy")
        proc = self.run_installer(target, "--copy")
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_an_unknown_position_exits_two(self):
        _target, proc = self.install("--position", "sideways")
        self.assertEqual(proc.returncode, 2)

    def test_a_manual_installation_is_refused(self):
        self.write("config.jsonc",
                   '{"modules-center": ["group/herdr-watchr"], "clock": {}}')
        _target, proc = self.install()
        self.assertEqual(proc.returncode, 1)

    def test_a_missing_waybar_config_is_refused(self):
        os.remove(os.path.join(self.waybar_dir, "config.jsonc"))
        _target, proc = self.install()
        self.assertEqual(proc.returncode, 1)


class TestExampleWaybarConfig(unittest.TestCase):
    def test_it_names_the_group_and_six_modules(self):
        text = (EXAMPLES / "waybar-config.jsonc").read_text(encoding="utf-8")
        self.assertIn('"group/herdr-watchr"', text)
        for status in hw.VOCABULARY:
            self.assertIn('"custom/herdr-%s"' % status, text)
        self.assertIn('"custom/herdr-watchr-notify"', text)

    def test_every_module_invokes_an_absolute_path(self):
        text = (EXAMPLES / "waybar-config.jsonc").read_text(encoding="utf-8")
        self.assertNotIn("~/.config/waybar/herdr", text)
        self.assertEqual(text.count('": "herdr-watchr'), 0)
        self.assertEqual(text.count('"exec": "~/.local/bin/herdr-watchr status'), 5)
        self.assertEqual(
            text.count('"on-click": "~/.local/bin/herdr-watchr focus-status'), 5)


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
