"""Test helpers: run each hook the way Claude Code does — as a subprocess fed JSON on stdin."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

HOOKS = Path(__file__).resolve().parent.parent / "hooks"


def iso(minutes_ago=0):
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()


def assistant(tokens, minutes_ago=0, **extra):
    """A main-agent reply whose usage block adds up to `tokens`."""
    entry = {
        "type": "assistant",
        "timestamp": iso(minutes_ago),
        "message": {"usage": {
            "input_tokens": 10,
            "cache_read_input_tokens": tokens - 110,
            "cache_creation_input_tokens": 50,
            "output_tokens": 50,
        }},
    }
    entry.update(extra)
    return entry


class HookCase(unittest.TestCase):
    """Gives every test an isolated plugin data dir and project dir."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="token-saver-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.data = self.tmp / "data"
        self.project = self.tmp / "project"
        (self.project / ".claude").mkdir(parents=True)

    def env(self, **overrides):
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("TS_", "CLAUDE_PLUGIN_OPTION_"))}
        env["CLAUDE_PLUGIN_DATA"] = str(self.data)
        env["CLAUDE_PROJECT_DIR"] = str(self.project)
        env.update({k: str(v) for k, v in overrides.items()})
        return env

    def run_hook(self, script, payload, raw=None, **env):
        """Returns (parsed stdout JSON or None, CompletedProcess)."""
        stdin = raw if raw is not None else json.dumps(payload)
        proc = subprocess.run(
            [sys.executable, str(HOOKS / script)],
            input=stdin.encode("utf-8"), capture_output=True, env=self.env(**env), timeout=30,
        )
        out = proc.stdout.decode("utf-8", "replace").strip()
        try:
            parsed = json.loads(out) if out else None
        except ValueError:
            parsed = None
        return parsed, proc

    def transcript(self, entries, name="transcript.jsonl"):
        path = self.tmp / name
        with open(path, "w", encoding="utf-8") as fh:
            for e in entries:
                fh.write((e if isinstance(e, str) else json.dumps(e)) + "\n")
        return str(path)

    def log_text(self):
        f = self.data / "hook.log"
        return f.read_text(encoding="utf-8") if f.exists() else ""

    @staticmethod
    def context(parsed):
        """The additionalContext a hook injected, or '' when it stayed silent."""
        return ((parsed or {}).get("hookSpecificOutput") or {}).get("additionalContext", "")
