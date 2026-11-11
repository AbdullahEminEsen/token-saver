"""Context guard: choosing a threshold, threshold handling, idle breaks, and missing or
unusual context data."""
import json
import time
import unittest

from helpers import HookCase, assistant, iso


class GuardCase(HookCase):
    THRESHOLDS = "150000,300000"  # what the user chose, unless a test says otherwise

    def guard(self, entries=None, prompt="fix the login bug", sid="s1", payload=None, **env):
        if self.THRESHOLDS:
            env.setdefault("TS_WARN_TOKENS", self.THRESHOLDS)
        if payload is None:
            payload = {"session_id": sid, "prompt": prompt}
            if entries is not None:
                payload["transcript_path"] = self.transcript(entries)
        parsed, proc = self.run_hook("context_guard.py", payload, **env)
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        self.assertEqual(proc.stderr, b"")
        return self.context(parsed)

    def assertWarns(self, ctx, kt=None):
        self.assertIn("[token-saver]", ctx)
        if kt:
            self.assertIn(kt, ctx)

    def assertSilent(self, ctx):
        self.assertEqual(ctx, "")


class Thresholds(GuardCase):
    def test_below_first_threshold_is_silent(self):
        self.assertSilent(self.guard([assistant(149_999)]))

    def test_exactly_at_threshold_warns(self):
        self.assertWarns(self.guard([assistant(150_000)]), "~150k tokens")

    def test_warns_once_per_threshold(self):
        entries = [assistant(152_000)]
        self.assertWarns(self.guard(entries), "~152k tokens")
        self.assertSilent(self.guard(entries))
        self.assertSilent(self.guard([assistant(200_000)]))

    def test_second_threshold_warns_again(self):
        self.assertWarns(self.guard([assistant(160_000)]))
        self.assertWarns(self.guard([assistant(310_000)]), "~310k tokens")
        self.assertSilent(self.guard([assistant(320_000)]))

    def test_jumping_past_both_thresholds_warns_once(self):
        self.assertWarns(self.guard([assistant(400_000)]))
        self.assertSilent(self.guard([assistant(410_000)]))

    def test_sessions_are_tracked_separately(self):
        entries = [assistant(152_000)]
        self.assertWarns(self.guard(entries, sid="a"))
        self.assertWarns(self.guard(entries, sid="b"))
        self.assertSilent(self.guard(entries, sid="a"))

    def test_threshold_rearms_after_context_shrinks(self):
        """After /compact the context drops; growing past the threshold again warns again."""
        self.assertWarns(self.guard([assistant(160_000)]))
        self.assertSilent(self.guard([assistant(40_000)]))
        self.assertWarns(self.guard([assistant(155_000)]))

    def test_custom_thresholds_from_env(self):
        self.assertSilent(self.guard([assistant(40_000)], TS_WARN_TOKENS="50000,90000"))
        self.assertWarns(self.guard([assistant(60_000)], TS_WARN_TOKENS="50000,90000"))
        self.assertWarns(self.guard([assistant(95_000)], TS_WARN_TOKENS="50000,90000"))

    def test_plugin_option_beats_env_var(self):
        ctx = self.guard([assistant(60_000)], TS_WARN_TOKENS="500000",
                         CLAUDE_PLUGIN_OPTION_WARN_TOKENS="50000")
        self.assertWarns(ctx)

    def test_threshold_formats(self):
        for raw in (" 50000 , 90000 ", "90000,50000", "50k", "50000.0", "50000;90000", "50000,,",
                    "50.000", "50,000", "50K, 90K", "0.05m", "50 bin"):
            with self.subTest(raw=raw):
                self.assertWarns(self.guard([assistant(60_000)], sid=f"fmt-{raw}",
                                            TS_WARN_TOKENS=raw))

    def test_bad_entries_are_skipped_not_fatal(self):
        self.assertWarns(self.guard([assistant(60_000)], TS_WARN_TOKENS="abc,50000,-5,0"))

    def test_unusable_setting_counts_as_not_set(self):
        """A setting with no readable number must not crash; the user is asked to choose."""
        for raw in ("abc", ",", "0", "-1", "nan", "inf", "5"):
            with self.subTest(raw=raw):
                ctx = self.guard([assistant(400_000)], sid=f"bad-{raw}", TS_WARN_TOKENS=raw)
                self.assertIn("First-time setup", ctx)

    def test_corrupt_state_file_is_treated_as_empty(self):
        state = self.data / "state"
        state.mkdir(parents=True)
        (state / "s1.warned").write_text("not numbers \x00")
        self.assertWarns(self.guard([assistant(152_000)]))
        self.assertSilent(self.guard([assistant(152_000)]))

    def test_odd_session_id_cannot_escape_state_dir(self):
        self.assertWarns(self.guard([assistant(152_000)], sid="../../evil"))
        self.assertFalse((self.tmp / "evil.warned").exists())
        self.assertEqual([p.parent for p in self.data.rglob("*.warned")], [self.data / "state"])


class ChoosingTheThreshold(GuardCase):
    """Nothing is built in: the user picks the number, in chat, the first time."""

    THRESHOLDS = None

    def saved(self):
        f = self.data / "config.json"
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None

    def test_first_prompt_asks_and_lets_the_request_continue(self):
        ctx = self.guard([assistant(40_000)])
        self.assertIn("First-time setup", ctx)
        self.assertIn("at how many tokens", ctx)
        self.assertIn("request as normal", ctx)
        self.assertIsNone(self.saved())

    def test_question_is_also_shown_to_the_user_directly(self):
        """Claude may skip the question; the notice from Claude Code itself can't be skipped."""
        parsed, proc = self.run_hook("context_guard.py", {"session_id": "s1", "prompt": "hi"})
        self.assertIn("no notification threshold set yet", parsed["systemMessage"])
        self.assertIn("token-saver off", parsed["systemMessage"])
        parsed, proc = self.run_hook("context_guard.py", {"session_id": "s1", "prompt": "100k"})
        self.assertNotIn("systemMessage", parsed)

    def test_asks_even_before_any_context_is_known(self):
        self.assertIn("First-time setup", self.guard())

    def test_no_warning_at_any_size_until_chosen(self):
        self.guard([assistant(40_000)])
        self.assertSilent(self.guard([assistant(900_000)]))

    def test_asks_once_per_session(self):
        self.assertIn("First-time setup", self.guard([assistant(40_000)]))
        self.assertSilent(self.guard([assistant(40_000)], prompt="now add a test"))
        self.assertIn("First-time setup", self.guard([assistant(40_000)], sid="next-session"))

    def test_answer_is_saved_and_confirmed(self):
        self.guard([assistant(40_000)])
        ctx = self.guard([assistant(40_000)], prompt="100k")
        self.assertIn("Saved", ctx)
        self.assertIn("100k tokens", ctx)
        self.assertEqual(self.saved()["levels"], [100_000])

    def test_answer_forms(self):
        for i, (answer, expected) in enumerate([
                ("120000", [120_000]), ("150k, 300k", [150_000, 300_000]),
                ("150k ve 300k", [150_000, 300_000]), ("~200k tokens.", [200_000]),
                ("1.5m", [1_500_000]), ("80.000", [80_000]), ("90 bin", [90_000])]):
            with self.subTest(answer=answer):
                sid = f"answer-{i}"
                (self.data / "config.json").unlink(missing_ok=True) if self.data.exists() else None
                self.guard([assistant(40_000)], sid=sid)
                self.guard([assistant(40_000)], sid=sid, prompt=answer)
                self.assertEqual(self.saved()["levels"], expected)

    def test_chosen_threshold_is_then_enforced(self):
        self.guard([assistant(40_000)])
        self.guard([assistant(40_000)], prompt="100k")
        self.assertSilent(self.guard([assistant(90_000)]))
        self.assertWarns(self.guard([assistant(101_000)]), "~101k tokens")
        self.assertSilent(self.guard([assistant(102_000)]))

    def test_chosen_threshold_applies_to_later_sessions_without_asking(self):
        self.guard([assistant(40_000)])
        self.guard([assistant(40_000)], prompt="100k")
        self.assertSilent(self.guard([assistant(40_000)], sid="later"))
        self.assertWarns(self.guard([assistant(120_000)], sid="later"))

    def test_an_ordinary_message_is_not_taken_as_the_answer(self):
        self.guard([assistant(40_000)])
        for prompt in ("fix issue 12345 now", "2", "use port 8080 please", "yes", "bump to v2.0.0"):
            with self.subTest(prompt=prompt):
                self.assertSilent(self.guard([assistant(40_000)], prompt=prompt))
                self.assertIsNone(self.saved())

    def test_a_number_is_not_an_answer_before_the_question(self):
        self.guard([assistant(40_000)], prompt="100k", sid="fresh")
        self.assertIsNone(self.saved())

    def test_settings_value_means_no_question(self):
        self.assertSilent(self.guard([assistant(40_000)], TS_WARN_TOKENS="100k"))
        self.assertWarns(self.guard([assistant(120_000)], TS_WARN_TOKENS="100k"))

    def test_settings_value_beats_the_saved_one(self):
        self.guard([assistant(40_000)])
        self.guard([assistant(40_000)], prompt="100k")
        self.assertSilent(self.guard([assistant(120_000)], sid="x", TS_WARN_TOKENS="500k"))

    def test_corrupt_config_counts_as_not_set(self):
        self.data.mkdir(parents=True)
        for junk in ("{oops", "[]", '{"levels": "150k"}', '{"levels": [5, null, "x"]}'):
            with self.subTest(junk=junk):
                (self.data / "config.json").write_text(junk)
                ctx = self.guard([assistant(400_000)], sid=f"junk-{len(junk)}")
                self.assertIn("First-time setup", ctx)


class Commands(GuardCase):
    """"token-saver ..." typed in chat changes or shows the setting, at any time."""

    THRESHOLDS = None

    def saved(self):
        return json.loads((self.data / "config.json").read_text(encoding="utf-8"))

    def test_set(self):
        for prompt in ("token-saver 200k", "Token-Saver: 200k", "/token-saver:threshold 200k",
                       "token-saver 200000"):
            with self.subTest(prompt=prompt):
                ctx = self.guard([assistant(40_000)], prompt=prompt)
                self.assertIn("Saved", ctx)
                self.assertEqual(self.saved()["levels"], [200_000])

    def test_change_replaces_the_old_value(self):
        self.guard(prompt="token-saver 200k")
        self.guard(prompt="token-saver 80k, 160k")
        self.assertEqual(self.saved()["levels"], [80_000, 160_000])
        self.assertWarns(self.guard([assistant(90_000)]))

    def test_off_stops_warnings_and_the_setup_question(self):
        ctx = self.guard(prompt="token-saver off")
        self.assertIn("now off", ctx)
        self.assertSilent(self.guard([assistant(900_000)]))
        self.assertSilent(self.guard([assistant(900_000)], sid="another"))

    def test_setting_a_number_turns_it_back_on(self):
        self.guard(prompt="token-saver kapat")
        self.guard(prompt="token-saver 100k")
        self.assertWarns(self.guard([assistant(150_000)]))

    def test_status(self):
        self.assertIn("not set yet", self.guard(prompt="token-saver status"))
        self.guard(prompt="token-saver 150k,300k")
        self.assertIn("150k and 300k tokens (saved)", self.guard(prompt="token-saver"))
        self.guard(prompt="token-saver off")
        self.assertIn("turned off", self.guard(prompt="token-saver durum"))
        self.assertIn("from settings", self.guard(prompt="token-saver status", TS_WARN_TOKENS="90k"))

    def test_saving_under_a_settings_override_says_so(self):
        ctx = self.guard(prompt="token-saver 200k", TS_WARN_TOKENS="90k")
        self.assertIn("takes priority", ctx)

    def test_a_sentence_about_the_plugin_is_not_a_command(self):
        self.guard(prompt="token-saver off")  # so the setup question stays out of the way
        for prompt in ("token-saver is great, how does it work?", "token-saver-foo 300000",
                       "token-saver set it to whatever you think"):
            with self.subTest(prompt=prompt):
                self.assertSilent(self.guard([assistant(40_000)], prompt=prompt))
        self.assertEqual(self.saved()["levels"], [])


class SkippedPrompts(GuardCase):
    def test_slash_commands_are_never_interrupted(self):
        self.assertSilent(self.guard([assistant(400_000)], prompt="/clear"))
        # ...and the threshold is still unused for the next real prompt
        self.assertWarns(self.guard([assistant(400_000)]))

    def test_handoff_requests_are_never_interrupted(self):
        self.assertSilent(self.guard([assistant(400_000)], prompt="write a Handoff please"))


class IdleBreak(GuardCase):
    def test_long_break_with_large_context_warns_once(self):
        entries = [assistant(80_000, minutes_ago=90)]
        ctx = self.guard(entries)
        self.assertWarns(ctx, "~80k tokens")
        self.assertIn("long break", ctx)
        self.assertSilent(self.guard(entries))

    def test_long_break_with_small_context_is_silent(self):
        self.assertSilent(self.guard([assistant(30_000, minutes_ago=90)]))

    def test_short_break_is_silent(self):
        self.assertSilent(self.guard([assistant(80_000, minutes_ago=20)]))

    def test_idle_minutes_is_configurable(self):
        self.assertWarns(self.guard([assistant(80_000, minutes_ago=20)], TS_IDLE_MINUTES="10"))

    def test_bad_idle_setting_falls_back_to_default(self):
        self.assertSilent(self.guard([assistant(80_000, minutes_ago=20)], TS_IDLE_MINUTES="soon"))
        self.assertWarns(self.guard([assistant(80_000, minutes_ago=90)], TS_IDLE_MINUTES="soon"))

    def test_unparseable_timestamp_is_not_a_break(self):
        e = assistant(80_000)
        e["timestamp"] = "yesterday-ish"
        self.assertSilent(self.guard([e]))

    def test_timestamp_with_z_suffix(self):
        e = assistant(80_000)
        e["timestamp"] = "2020-01-01T00:00:00.000Z"
        self.assertWarns(self.guard([e]))


class UnusualContextData(GuardCase):
    """None of these may crash, print garbage, or warn on a wrong number."""

    def test_empty_stdin(self):
        parsed, proc = self.run_hook("context_guard.py", None, raw="")
        self.assertEqual((proc.returncode, proc.stdout, proc.stderr), (0, b"", b""))

    def test_invalid_json_stdin(self):
        parsed, proc = self.run_hook("context_guard.py", None, raw="{not json")
        self.assertEqual((proc.returncode, proc.stdout, proc.stderr), (0, b"", b""))

    def test_non_object_json_stdin(self):
        for raw in ("[]", "null", '"text"', "42"):
            with self.subTest(raw=raw):
                parsed, proc = self.run_hook("context_guard.py", None, raw=raw)
                self.assertEqual((proc.returncode, proc.stdout, proc.stderr), (0, b"", b""))

    def test_no_transcript_path(self):
        self.assertSilent(self.guard())
        self.assertIn("context size unknown", self.log_text())

    def test_missing_context_data_before_a_threshold_is_chosen(self):
        for raw in ("", "{oops", "[]", "null"):
            with self.subTest(raw=raw):
                parsed, proc = self.run_hook("context_guard.py", None, raw=raw)
                self.assertEqual((proc.returncode, proc.stdout, proc.stderr), (0, b"", b""))

    def test_null_fields(self):
        self.assertSilent(self.guard(payload={"session_id": None, "prompt": None,
                                              "transcript_path": None}))

    def test_missing_transcript_file(self):
        self.assertSilent(self.guard(payload={"session_id": "s1", "prompt": "hi",
                                              "transcript_path": str(self.tmp / "nope.jsonl")}))

    def test_transcript_path_is_a_directory(self):
        self.assertSilent(self.guard(payload={"session_id": "s1", "prompt": "hi",
                                              "transcript_path": str(self.tmp)}))

    def test_empty_transcript(self):
        self.assertSilent(self.guard([]))

    def test_transcript_without_any_usage(self):
        self.assertSilent(self.guard([
            {"type": "user", "timestamp": iso(), "message": {"content": "hi"}},
            {"type": "assistant", "timestamp": iso(), "message": {"content": "hello"}},
        ]))

    def test_garbage_lines_are_skipped(self):
        self.assertWarns(self.guard([
            assistant(152_000),
            "{truncated json",
            "",
            "[1, 2, 3]",
            '"just a string"',
            "null",
        ]), "~152k tokens")

    def test_binary_junk_in_transcript(self):
        path = self.transcript([assistant(152_000)])
        with open(path, "ab") as fh:
            fh.write(b"\xff\xfe\x00\x9c broken \xc3\n")
        self.assertWarns(self.guard(payload={"session_id": "s1", "prompt": "hi",
                                             "transcript_path": path}))

    def test_subagent_usage_is_ignored(self):
        """A subagent's context is not the main conversation's context."""
        self.assertSilent(self.guard([
            assistant(40_000),
            assistant(400_000, isSidechain=True),
        ]))

    def test_latest_main_reply_wins(self):
        self.assertSilent(self.guard([assistant(400_000), assistant(40_000)]))

    def test_all_zero_usage_block_is_skipped(self):
        """Synthetic/error replies report zero usage; the real number is the reply before."""
        zero = assistant(152_000)
        zero["message"]["usage"] = {"input_tokens": 0, "output_tokens": 0}
        self.assertWarns(self.guard([assistant(152_000), zero]), "~152k tokens")

    def test_null_and_missing_usage_fields(self):
        e = assistant(0)
        e["message"]["usage"] = {"input_tokens": 152_000, "cache_read_input_tokens": None}
        self.assertWarns(self.guard([e]), "~152k tokens")

    def test_wrongly_typed_usage_fields(self):
        e = assistant(0)
        e["message"]["usage"] = {"input_tokens": "lots", "cache_read_input_tokens": 152_000,
                                 "output_tokens": [1], "cache_creation_input_tokens": True}
        self.assertWarns(self.guard([e]), "~152k tokens")

    def test_wrongly_typed_message_and_usage(self):
        entries = [assistant(152_000)]
        for bad in ("text", None, 7, ["x"]):
            entries.append({"type": "assistant", "timestamp": iso(), "message": bad})
            entries.append({"type": "assistant", "timestamp": iso(), "message": {"usage": bad}})
        self.assertWarns(self.guard(entries), "~152k tokens")

    def test_only_tail_of_huge_transcript_is_read(self):
        filler = {"type": "user", "timestamp": iso(), "message": {"content": "x" * 5000}}
        self.assertWarns(self.guard([assistant(40_000)] + [filler] * 600 + [assistant(152_000)]))


class StatuslineFallback(GuardCase):
    def write_state(self, pct, size=200_000, age=0, sid="s1"):
        state = self.data / "state"
        state.mkdir(parents=True, exist_ok=True)
        (state / f"{sid}.json").write_text(json.dumps(
            {"used_percentage": pct, "context_window_size": size, "ts": time.time() - age}))

    def test_used_when_transcript_is_unavailable(self):
        self.write_state(80)  # 80% of 200k = 160k
        self.assertWarns(self.guard(), "~160k tokens")

    def test_window_size_is_respected(self):
        self.write_state(20, size=1_000_000)
        self.assertWarns(self.guard(), "~200k tokens")

    def test_stale_value_is_ignored(self):
        self.write_state(80, age=3600)
        self.assertSilent(self.guard())

    def test_transcript_takes_priority(self):
        self.write_state(90)
        self.assertSilent(self.guard([assistant(40_000)]))

    def test_corrupt_state_is_ignored(self):
        state = self.data / "state"
        state.mkdir(parents=True)
        (state / "s1.json").write_text("{oops")
        self.assertSilent(self.guard())


class WarningText(GuardCase):
    """The instruction Claude receives is what keeps the user's request from getting lost."""

    def test_tells_claude_to_ask_first_and_keep_the_request_verbatim(self):
        ctx = self.guard([assistant(152_000)])
        self.assertIn("BEFORE starting", ctx)
        self.assertIn("Call no tools", ctx)
        self.assertIn(".token-saver/handoff.md", ctx)
        self.assertNotIn(".claude/handoff", ctx)
        self.assertIn('never say "Done" without it', ctx)
        self.assertIn("VERBATIM", ctx)
        self.assertIn('"## Pending request"', ctx)
        self.assertIn("If the user says no", ctx)

    def test_output_is_valid_hook_json(self):
        parsed, proc = self.run_hook("context_guard.py", {
            "session_id": "s1", "prompt": "hi",
            "transcript_path": self.transcript([assistant(152_000)])}, TS_WARN_TOKENS="150k")
        self.assertEqual(parsed["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
        proc.stdout.decode("ascii")  # safe on any console code page


if __name__ == "__main__":
    unittest.main()
