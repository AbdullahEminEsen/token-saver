"""Status line output, shared option lookup, and the plugin manifests."""
import json
import re
import unittest
from pathlib import Path

from helpers import HOOKS, HookCase

ROOT = HOOKS.parent
ANSI = re.compile(r"\x1b\[\d+m")


class Statusline(HookCase):
    def line(self, payload=None, raw=None):
        parsed, proc = self.run_hook("statusline.py", payload, raw=raw,
                                     PYTHONIOENCODING="cp1252", PYTHONUTF8="0")
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        return proc.stdout.decode("utf-8").strip()

    def payload(self, pct, size=200_000):
        return {"session_id": "s1", "model": {"display_name": "Opus"},
                "context_window": {"used_percentage": pct, "context_window_size": size},
                "rate_limits": {"five_hour": {"used_percentage": 23}}}

    def test_full_line(self):
        out = self.line(self.payload(41))
        self.assertEqual(ANSI.sub("", out), "Opus | ctx ████░░░░░░ 41% (82k/200k) | 5h 23%")
        self.assertIn("\x1b[32m", out)  # green under 150k

    def test_colors_follow_the_guard_thresholds(self):
        self.assertIn("\x1b[33m", self.line(self.payload(80)))                  # 160k: yellow
        self.assertIn("\x1b[31m", self.line(self.payload(35, size=1_000_000)))  # 350k: red

    def test_saves_state_for_the_guard_fallback(self):
        self.line(self.payload(41))
        state = json.loads((self.data / "state" / "s1.json").read_text())
        self.assertEqual((state["used_percentage"], state["context_window_size"]), (41, 200_000))

    def test_missing_context_data(self):
        self.assertEqual(self.line({"model": {"display_name": "Opus"}}), "Opus")
        self.assertEqual(self.line({}), "")
        self.assertEqual(self.line({"context_window": None, "model": None, "rate_limits": None}), "")

    def test_bad_stdin(self):
        for raw in ("", "{oops", "[]"):
            with self.subTest(raw=raw):
                self.assertEqual(self.line(raw=raw), "ctx ?")


class Options(HookCase):
    def test_env_var_names_in_readme_match_the_code(self):
        """Every TS_* variable the README documents must be one a hook actually reads."""
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        documented = set(re.findall(r"`(TS_[A-Z_]+)`", readme))
        self.assertTrue(documented)
        code = "".join(p.read_text(encoding="utf-8") for p in HOOKS.glob("*.py"))
        read = {"TS_" + name.upper() for name in re.findall(r'(?:opt|num)\("([a-z_]+)"', code)}
        self.assertLessEqual(documented, read)


class Manifests(unittest.TestCase):
    def load(self, rel):
        return json.loads((ROOT / rel).read_text(encoding="utf-8"))

    def test_plugin_manifest(self):
        plugin = self.load(".claude-plugin/plugin.json")
        self.assertEqual(plugin["name"], "token-saver")
        self.assertRegex(plugin["version"], r"^\d+\.\d+\.\d+$")

    def test_user_config_options_are_read_by_the_hooks(self):
        plugin = self.load(".claude-plugin/plugin.json")
        code = "".join(p.read_text(encoding="utf-8") for p in HOOKS.glob("*.py"))
        for name in plugin["userConfig"]:
            with self.subTest(option=name):
                self.assertIn(f'"{name}"', code)

    def test_default_thresholds_agree(self):
        plugin = self.load(".claude-plugin/plugin.json")
        guard = (HOOKS / "context_guard.py").read_text(encoding="utf-8")
        default = plugin["userConfig"]["warn_tokens"]["default"]
        self.assertIn(f'DEFAULT_LEVELS = "{default}"', guard)

    def test_marketplace_lists_the_plugin(self):
        market = self.load(".claude-plugin/marketplace.json")
        self.assertEqual([p["name"] for p in market["plugins"]], ["token-saver"])

    def test_hooks_json_points_at_existing_scripts(self):
        hooks = self.load("hooks/hooks.json")["hooks"]
        self.assertEqual(set(hooks), {"UserPromptSubmit", "SessionStart", "PreToolUse"})
        for groups in hooks.values():
            for group in groups:
                for hook in group["hooks"]:
                    for script in re.findall(r"/hooks/(\w+\.py)", hook["command"]):
                        self.assertTrue((HOOKS / script).exists(), script)

    def test_changelog_covers_the_current_version(self):
        version = self.load(".claude-plugin/plugin.json")["version"]
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn(f"## [{version}]", changelog)


if __name__ == "__main__":
    unittest.main()
