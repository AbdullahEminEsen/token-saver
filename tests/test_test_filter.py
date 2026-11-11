"""Test filter: which commands get rewritten, and that the rewrite keeps the exit code."""
import os
import shutil
import stat
import subprocess
import sys
import unittest

from helpers import HookCase


def find_bash():
    bash = shutil.which("bash")
    if not bash:
        return None
    if sys.platform == "win32" and "system32" in bash.lower():
        return None  # the WSL launcher, not a usable bash
    return bash


class FilterCase(HookCase):
    def rewrite(self, command, **env):
        payload = {"tool_name": "Bash", "tool_input": {"command": command, "timeout": 5000}}
        parsed, proc = self.run_hook("test_filter.py", payload, **env)
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        if not parsed:
            return None
        out = parsed["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "PreToolUse")
        self.assertEqual(out["updatedInput"]["timeout"], 5000, "other tool input must be kept")
        return out["updatedInput"]["command"]


class Matching(FilterCase):
    def test_test_commands_are_rewritten(self):
        for cmd in ("pytest", "pytest -x tests/test_a.py", "python -m pytest -q",
                    "python3 -m pytest", "npm test", "npm run test", "pnpm test", "yarn test",
                    "go test ./...", "cargo test --release", "php artisan test --filter=Login",
                    "vendor/bin/phpunit", "./vendor/bin/pest", "  pytest  "):
            with self.subTest(cmd=cmd):
                new = self.rewrite(cmd)
                self.assertIsNotNone(new)
                self.assertIn(cmd.strip(), new)

    def test_other_commands_are_left_alone(self):
        for cmd in ("ls -la", "git status", "npm install", "npm run build", "echo pytest",
                    "pytester", "python script.py", ""):
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.rewrite(cmd))

    def test_compound_commands_are_left_alone(self):
        """Chains, pipes, redirects and substitutions can't be wrapped safely."""
        for cmd in ("pytest && echo ok", "pytest; rm -rf x", "pytest | tee log", "pytest > out.txt",
                    "pytest $(cat args)", "pytest `cat args`", "pytest -k $NAME", "pytest\nls",
                    "cd app && npm test"):
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.rewrite(cmd))

    def test_can_be_disabled(self):
        for off in ("0", "false", "no"):
            with self.subTest(off=off):
                self.assertIsNone(self.rewrite("pytest", TS_TEST_FILTER=off))

    def test_unusual_input_is_a_noop(self):
        for raw in ("", "{oops", "[]", "null", '{"tool_input": null}',
                    '{"tool_input": "pytest"}', '{"tool_input": {"command": null}}',
                    '{"tool_input": {"command": 5}}'):
            with self.subTest(raw=raw):
                parsed, proc = self.run_hook("test_filter.py", None, raw=raw)
                self.assertEqual((proc.returncode, proc.stderr), (0, b""))
                self.assertEqual(parsed, {})


@unittest.skipUnless(find_bash(), "needs bash")
class Execution(FilterCase):
    """Runs the rewritten command for real against a fake `pytest` on PATH."""

    def fake_pytest(self, body):
        bindir = self.tmp / "bin"
        bindir.mkdir(exist_ok=True)
        script = bindir / "pytest"
        script.write_bytes(("#!/usr/bin/env bash\n" + body).encode("utf-8"))
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        return bindir

    def execute(self, body, command="pytest"):
        bindir = self.fake_pytest(body)
        new = self.rewrite(command)
        env = self.env(PATH=str(bindir) + os.pathsep + os.environ["PATH"])
        proc = subprocess.run([find_bash(), "-c", new], capture_output=True, env=env,
                              cwd=str(self.tmp), timeout=60)
        return proc.returncode, proc.stdout.decode("utf-8", "replace")

    def test_failures_and_tail_survive_passing_noise_is_dropped(self):
        rc, out = self.execute(
            'for i in $(seq 1 300); do echo "tests/test_$i.py::test_ok PASSED"; done\n'
            'echo "FAILED tests/test_login.py::test_double_click - AssertionError"\n'
            'echo "=== 1 failed, 300 passed in 2.31s ==="\n'
            'exit 1\n')
        self.assertEqual(rc, 1)
        self.assertIn("FAILED tests/test_login.py::test_double_click", out)
        self.assertIn("1 failed, 300 passed", out)
        self.assertIn("--- tail ---", out)
        self.assertNotIn("test_150.py", out)
        self.assertLess(len(out.splitlines()), 20)
        self.assertRegex(out, r"\[token-saver: full output\s+302 lines in ")

    def test_exit_code_is_preserved(self):
        for code in (0, 2, 5):
            with self.subTest(code=code):
                rc, out = self.execute(f'echo "collected 3 items"\nexit {code}\n')
                self.assertEqual(rc, code)

    def test_stderr_is_captured_too(self):
        rc, out = self.execute('echo "Error: cannot import module" >&2\nexit 4\n')
        self.assertEqual(rc, 4)
        self.assertIn("Error: cannot import module", out)

    def test_arguments_reach_the_test_command(self):
        rc, out = self.execute('echo "args=$*"\n', command="pytest -x tests/a.py")
        self.assertIn("args=-x tests/a.py", out)

    def test_huge_failure_output_is_capped(self):
        rc, out = self.execute('for i in $(seq 1 500); do echo "ERROR line $i"; done\nexit 1\n')
        self.assertEqual(rc, 1)
        self.assertLess(len(out.splitlines()), 140)


if __name__ == "__main__":
    unittest.main()
