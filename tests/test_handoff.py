"""Handoff: the pending request must survive the trip into the fresh session, untouched."""
import os
import re
import time
import unittest
from pathlib import Path

from helpers import HookCase

SKILL = Path(__file__).resolve().parent.parent / "skills" / "handoff" / "SKILL.md"

PENDING = """Şu login bug'ını düzelt: "Giriş yap" butonu 2. tıklamada çalışmıyor — ama `auth.ts`'e dokunma!
  1) önce test yaz   (girinti korunmalı)
  2) sonra düzelt 🚀 <b>html</b> & $HOME %PATH% \\n \\\\ {{braces}}"""

HANDOFF = f"""# Handoff — login fix (2026-11-11 14:30)

## Goal
Fix the login flow without touching auth.ts.

## Pending request
{PENDING}

## Done so far
- src/login.tsx:40-62 — debounce added, double submit prevented

## Open issues / next steps
1. Write the failing test first
"""


class StartCase(HookCase):
    def start(self, source="clear", payload=None, **env):
        if payload is None:
            payload = {"source": source, "cwd": str(self.project)}
        parsed, proc = self.run_hook("session_start.py", payload, **env)
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        self.assertEqual(proc.stderr, b"")
        return self.context(parsed)

    def write_handoff(self, text=HANDOFF, age_hours=0, encoding="utf-8", folder=".token-saver"):
        f = self.project / folder / "handoff.md"
        f.parent.mkdir(exist_ok=True)
        f.write_bytes(text.encode(encoding))
        if age_hours:
            t = time.time() - age_hours * 3600
            os.utime(f, (t, t))
        return f


def pending_section(text):
    m = re.search(r"^## Pending request\n(.*?)(?=^## )", text, re.S | re.M)
    return m.group(1).rstrip("\n") if m else None


class PendingRequestPreserved(StartCase):
    def test_pending_request_arrives_byte_for_byte(self):
        self.write_handoff()
        ctx = self.start("clear")
        self.assertEqual(pending_section(ctx), PENDING)

    def test_whole_handoff_is_loaded(self):
        self.write_handoff()
        ctx = self.start("clear")
        self.assertIn(HANDOFF.strip(), ctx)
        self.assertIn("Handoff from the previous session", ctx)
        self.assertIn('carry out\nthe "Pending request" directly', ctx)

    def test_loaded_on_startup_too(self):
        self.write_handoff()
        self.assertEqual(pending_section(self.start("startup")), PENDING)

    def test_windows_line_endings_and_bom(self):
        self.write_handoff("﻿" + HANDOFF.replace("\n", "\r\n"))
        ctx = self.start("clear")
        self.assertNotIn("﻿", ctx)
        self.assertEqual(pending_section(ctx.replace("\r\n", "\n")), PENDING)

    def test_non_utf8_file_still_loads(self):
        self.write_handoff("## Pending request\ncafé ünlü\n## Done\n", encoding="cp1254")
        ctx = self.start("clear")
        self.assertIn("## Pending request", ctx)

    def test_long_pending_request_is_not_truncated(self):
        long_request = "\n".join(f"step {i}: do the thing number {i}" for i in range(400))
        self.write_handoff(HANDOFF.replace(PENDING, long_request))
        self.assertEqual(pending_section(self.start("clear")), long_request)

    def test_project_dir_from_cwd_when_env_is_missing(self):
        self.write_handoff()
        ctx = self.start(payload={"source": "clear", "cwd": str(self.project)},
                         CLAUDE_PROJECT_DIR="")
        self.assertEqual(pending_section(ctx), PENDING)


class LegacyLocation(StartCase):
    """v1.0 wrote .claude/handoff.md; a handoff written before upgrading must still load."""

    def test_legacy_handoff_is_loaded_and_consumed(self):
        f = self.write_handoff(folder=".claude")
        self.assertEqual(pending_section(self.start("clear")), PENDING)
        self.assertFalse(f.exists())
        self.assertTrue(f.with_name("handoff.done.md").exists())

    def test_current_location_wins_over_legacy(self):
        legacy = self.write_handoff("## Pending request\nold one\n## Done\n", folder=".claude")
        self.write_handoff()
        self.assertEqual(pending_section(self.start("clear")), PENDING)
        self.assertTrue(legacy.exists())

    def test_a_folder_named_handoff_md_is_not_a_handoff(self):
        (self.project / ".token-saver" / "handoff.md").mkdir(parents=True)
        self.assertNotIn("Handoff from the previous session", self.start("clear"))


class UsedOnce(StartCase):
    def test_handoff_is_consumed(self):
        f = self.write_handoff()
        self.start("clear")
        self.assertFalse(f.exists())
        done = f.with_name("handoff.done.md")
        self.assertEqual(done.read_text(encoding="utf-8"), HANDOFF)

    def test_second_session_does_not_get_it_again(self):
        self.write_handoff()
        self.assertIn("Pending request", self.start("clear"))
        self.assertNotIn("Pending request", self.start("clear"))

    def test_new_handoff_replaces_an_old_done_file(self):
        self.write_handoff("old handoff")
        self.start("clear")
        f = self.write_handoff()
        self.assertEqual(pending_section(self.start("clear")), PENDING)
        self.assertEqual(f.with_name("handoff.done.md").read_text(encoding="utf-8"), HANDOFF)


class NotLoaded(StartCase):
    def test_compact_keeps_the_handoff_for_the_next_clear(self):
        f = self.write_handoff()
        self.assertNotIn("Pending request", self.start("compact"))
        self.assertTrue(f.exists())

    def test_stale_handoff_is_ignored(self):
        f = self.write_handoff(age_hours=25)
        self.assertNotIn("Pending request", self.start("clear"))
        self.assertTrue(f.exists())

    def test_max_age_is_configurable(self):
        self.write_handoff(age_hours=25)
        self.assertIn("Pending request", self.start("clear", TS_HANDOFF_MAX_AGE_H="48"))

    def test_bad_max_age_falls_back_to_24h(self):
        self.write_handoff(age_hours=2)
        self.assertIn("Pending request", self.start("clear", TS_HANDOFF_MAX_AGE_H="a day"))

    def test_empty_handoff_is_ignored(self):
        self.write_handoff("  \n\n")
        self.assertNotIn("Handoff from the previous session", self.start("clear"))

    def test_no_handoff_file(self):
        ctx = self.start("clear")
        self.assertNotIn("Handoff from the previous session", ctx)
        self.assertIn("Working rules", ctx)


class WorkingRules(StartCase):
    def test_rules_are_injected_by_default(self):
        self.assertIn("[token-saver] Working rules", self.start("startup"))

    def test_rules_can_be_disabled(self):
        for off in ("0", "false", "False", "no"):
            with self.subTest(off=off):
                parsed, proc = self.run_hook("session_start.py", {"source": "startup"},
                                             TS_INJECT_RULES=off)
                self.assertEqual((proc.returncode, proc.stdout.strip()), (0, b""))

    def test_handoff_still_loads_with_rules_disabled(self):
        self.write_handoff()
        ctx = self.start("clear", TS_INJECT_RULES="0")
        self.assertNotIn("Working rules", ctx)
        self.assertEqual(pending_section(ctx), PENDING)

    def test_compaction_rule_keeps_pending_request(self):
        self.assertIn("pending request verbatim", self.start("compact"))

    def test_bad_stdin_still_injects_rules(self):
        for raw in ("", "{oops", "[]", "null"):
            with self.subTest(raw=raw):
                parsed, proc = self.run_hook("session_start.py", None, raw=raw)
                self.assertEqual(proc.returncode, 0)
                self.assertIn("Working rules", self.context(parsed))

    def test_output_is_ascii_safe_json(self):
        self.write_handoff()
        parsed, proc = self.run_hook("session_start.py", {"source": "clear"})
        proc.stdout.decode("ascii")
        self.assertEqual(parsed["hookSpecificOutput"]["hookEventName"], "SessionStart")


class SkillTemplate(unittest.TestCase):
    """The skill is a prompt, so the test pins the parts the hooks depend on."""

    def setUp(self):
        self.text = SKILL.read_text(encoding="utf-8")

    def test_writes_to_the_path_the_loader_reads(self):
        self.assertIn("`.token-saver/handoff.md`", self.text)
        self.assertNotIn(".claude/handoff", self.text)

    def test_never_reports_done_without_the_file(self):
        self.assertIn("Only after the file is written", self.text)
        self.assertIn("If the write failed or was denied", self.text)

    def test_template_has_a_verbatim_pending_request_section(self):
        section = pending_section(self.text)
        self.assertIsNotNone(section, "template lost its '## Pending request' section")
        self.assertIn("VERBATIM", section)

    def test_frontmatter_names_the_skill(self):
        self.assertTrue(self.text.startswith("---\nname: handoff\n"))


if __name__ == "__main__":
    unittest.main()
