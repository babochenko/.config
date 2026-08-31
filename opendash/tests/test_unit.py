"""Level 1: pure functions -- no server, no database, no tmux, no git."""
from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from support import ROOT, SandboxCase  # noqa: F401  (ROOT puts opendash on sys.path)

import dashboard
import ocore


class Tickets(unittest.TestCase):
    def test_plain_ticket(self):
        self.assertEqual(ocore.extract_ticket("PROJ-1204 fix the retry"), "PROJ-1204")

    def test_from_a_jira_url(self):
        self.assertEqual(
            ocore.extract_ticket("see https://x.atlassian.net/browse/plat-99 please"),
            "PLAT-99")

    def test_url_wins_over_a_bare_match(self):
        self.assertEqual(
            ocore.extract_ticket("ABC-1 and /browse/XYZ-2"), "XYZ-2")

    def test_only_across_the_first_line_is_not_required(self):
        self.assertEqual(ocore.extract_ticket("first line\nPROJ-7 later"), "PROJ-7")

    def test_no_ticket(self):
        self.assertIsNone(ocore.extract_ticket("just do the thing"))
        self.assertIsNone(ocore.extract_ticket(""))

    def test_lowercase_alone_is_not_a_ticket(self):
        self.assertIsNone(ocore.extract_ticket("abc-12 lowercase"))


class Headline(unittest.TestCase):
    def test_manual_name_wins_over_generated_title(self):
        item = {"title_override": "my name", "title": "generated", "task": "t"}
        self.assertEqual(ocore._headline(item), "my name")

    def test_generated_title_wins_over_the_task(self):
        self.assertEqual(ocore._headline({"title": "generated", "task": "t"}), "generated")

    def test_falls_back_to_the_first_line_of_a_multiline_task(self):
        item = {"task": "first line of the request\nsecond line\nthird"}
        self.assertEqual(ocore._headline(item), "first line of the request")

    def test_ticket_is_stripped_because_it_has_its_own_column(self):
        item = {"ticket": "PROJ-1", "title": "PROJ-1: fix the thing"}
        self.assertEqual(ocore._headline(item), "fix the thing")

    def test_a_title_that_is_only_the_ticket_is_kept(self):
        item = {"ticket": "PROJ-1", "title": "PROJ-1"}
        self.assertEqual(ocore._headline(item), "PROJ-1")

    def test_no_task_at_all(self):
        self.assertEqual(ocore._headline({}), "(no task)")


class AgentName(unittest.TestCase):
    def test_manual_name_wins_over_live_agent(self):
        item = {"title_override": "[OPENDASH]", "agent_live": "build", "agent": "myagent"}
        self.assertEqual(ocore.display_agent(item), "[OPENDASH]")

    def test_live_agent_wins_when_there_is_no_manual_name(self):
        self.assertEqual(ocore.display_agent({"agent_live": "build", "agent": "myagent"}), "build")


class Line2(unittest.TestCase):
    def test_working_prefers_the_in_progress_todo(self):
        item = {"state": "working", "activity": ("running", "bash npm test"),
                "todos": [{"status": "in_progress", "content": "wire the client"}]}
        self.assertIn("wire the client", ocore.worked_on(item))
        self.assertIn("bash npm test", ocore.worked_on(item))

    def test_working_with_nothing_to_say(self):
        self.assertEqual(ocore.worked_on(
            {"state": "working", "activity": ("none", ""), "todos": []}), "thinking…")

    def test_idle_reports_what_it_said(self):
        item = {"state": "idle", "activity": ("said", "Done. Added the retry."), "todos": []}
        self.assertEqual(ocore.worked_on(item), "Done. Added the retry.")

    def test_error_shows_the_error(self):
        item = {"state": "error", "error": "boom", "activity": ("none", ""), "todos": []}
        self.assertEqual(ocore.worked_on(item), "boom")

    def test_queued_says_so(self):
        item = {"state": "queued", "activity": ("none", ""), "todos": []}
        self.assertIn("queued", ocore.worked_on(item))

    def test_progress_counts_completed_todos(self):
        item = {"todos": [{"status": "completed", "content": "a"},
                          {"status": "in_progress", "content": "b"},
                          {"status": "pending", "content": "c"}]}
        self.assertEqual(ocore._progress(item), "✓1/3")

    def test_progress_is_blank_without_todos(self):
        self.assertEqual(ocore._progress({"todos": []}), "")


class TypedCommand(unittest.TestCase):
    def test_drops_the_interpreter_and_the_path(self):
        self.assertEqual(
            ocore._typed_command("/bin/sh ./gradlew test --tests RetrySpec"),
            "gradlew test --tests RetrySpec")

    def test_keeps_a_plain_binary_with_its_arguments(self):
        self.assertEqual(ocore._typed_command("/usr/bin/yes hello"), "yes hello")

    def test_a_bare_shell_is_left_alone(self):
        self.assertEqual(ocore._typed_command("-zsh"), "-zsh")

    def test_empty(self):
        self.assertEqual(ocore._typed_command(""), "")


class Ordering(unittest.TestCase):
    def test_start_time_orders_by_default(self):
        items = [{"session_id": "b", "created": 200}, {"session_id": "a", "created": 100}]
        self.assertEqual([i["session_id"] for i in ocore.sort_items(items)], ["a", "b"])

    def test_a_manual_order_overrides_start_time(self):
        items = [{"session_id": "b", "created": 200, "order": 50},
                 {"session_id": "a", "created": 100}]
        self.assertEqual([i["session_id"] for i in ocore.sort_items(items)], ["b", "a"])

    def test_state_never_reorders(self):
        items = [{"session_id": "a", "created": 100, "state": "idle"},
                 {"session_id": "b", "created": 200, "state": "attention"}]
        self.assertEqual([i["session_id"] for i in ocore.sort_items(items)], ["a", "b"])

    def test_order_key_ignores_a_bool(self):
        self.assertEqual(ocore.order_key({"order": True, "created": 7}), 7.0)


class Models(unittest.TestCase):
    def test_provider_and_model_are_split(self):
        self.assertEqual(ocore._split_model("anthropic/claude-sonnet-5"),
                         {"providerID": "anthropic", "modelID": "claude-sonnet-5"})

    def test_nonsense_is_ignored(self):
        self.assertIsNone(ocore._split_model("no-slash"))
        self.assertIsNone(ocore._split_model(None))


class GitStatus(unittest.TestCase):
    def test_runs_the_repo_colored_git_status_function(self):
        result = type("Result", (), {"stdout": "green", "stderr": "", "returncode": 0})()
        with patch.object(ocore.subprocess, "run", return_value=result) as run:
            self.assertEqual(ocore.git_status_output("/tmp/project"), ("green", 0))
        self.assertEqual(run.call_args.args[0], ["zsh", "-lic", "git-status --tree"])

    def test_ansi_segments_preserve_git_status_colors(self):
        self.assertEqual(
            dashboard._ansi_segments("\033[32m+3\033[0m -1"),
            [("+3", dashboard.C_OK), (" -1", dashboard.C_DIM)],
        )


class Permissions(unittest.TestCase):
    def test_unattended_by_default_like_opencode_auto(self):
        with patch.dict(os.environ, {}, clear=True):
            permissions = json.loads(ocore.permission_json())
        self.assertEqual(permissions["bash"], "allow")
        self.assertEqual(permissions["edit"], "allow")

    def test_read_only_is_the_opt_in(self):
        with patch.dict(os.environ, {"OPENDASH_AUTO": "0"}, clear=True):
            permissions = json.loads(ocore.permission_json())
        self.assertEqual(permissions["read"], "allow")
        self.assertNotIn("bash", permissions)

    def test_a_bare_string_is_rejected_because_opencode_merges_it(self):
        with patch.dict(os.environ, {"OPENDASH_PERMISSION": '"allow"'}, clear=True):
            with self.assertRaises(ocore.ApiError):
                ocore.permission_json()

    def test_invalid_json_is_rejected(self):
        with patch.dict(os.environ, {"OPENDASH_PERMISSION": "{oops"}, clear=True):
            with self.assertRaises(ocore.ApiError):
                ocore.permission_json()


class Ages(unittest.TestCase):
    def test_units(self):
        now = ocore.now_ms()
        self.assertEqual(ocore.fmt_age(now - 5_000), "5s")
        self.assertEqual(ocore.fmt_age(now - 120_000), "2m")
        self.assertEqual(ocore.fmt_age(now - 3 * 3_600_000), "3h00")
        self.assertEqual(ocore.fmt_age(now - 2 * 86_400_000), "2d")

    def test_missing(self):
        self.assertEqual(ocore.fmt_age(None), "")


class LaunchFailure(SandboxCase):
    def test_reads_the_servers_own_reason_from_the_log(self):
        log = self.box.dir / "opencode.log"
        log.write_text(
            'timestamp=1 level=INFO message=created id=ses_x\n'
            'timestamp=2 level=ERROR message="prompt_async failed" sessionID=ses_x'
            ' cause="Cause([Die(UnknownError: UnknownError)])"\n')
        with patch.object(self.ocore, "opencode_log", return_value=log):
            reason = self.ocore.launch_failure("ses_x")
        self.assertIn("prompt_async failed", reason)
        self.assertIn("UnknownError", reason)

    def test_no_error_for_this_session(self):
        log = self.box.dir / "opencode.log"
        log.write_text("timestamp=1 level=ERROR message=other sessionID=ses_other\n")
        with patch.object(self.ocore, "opencode_log", return_value=log):
            self.assertIsNone(self.ocore.launch_failure("ses_x"))

    def test_a_missing_log_is_not_an_error(self):
        with patch.object(self.ocore, "opencode_log",
                          return_value=self.box.dir / "nope.log"):
            self.assertIsNone(self.ocore.launch_failure("ses_x"))


class Clipping(unittest.TestCase):
    def test_short_text_is_untouched(self):
        self.assertEqual(dashboard.clip("hello", 10), "hello")

    def test_long_text_gets_an_ellipsis_and_fits(self):
        out = dashboard.clip("abcdefghij", 5)
        self.assertTrue(out.endswith("…"))
        self.assertLessEqual(len(out), 5)

    def test_wide_characters_are_counted_as_two_columns(self):
        self.assertLessEqual(sum(dashboard._w(c) for c in dashboard.clip("日本語テスト", 6)), 6)

    def test_zero_width(self):
        self.assertEqual(dashboard.clip("abc", 0), "")


class ShortDir(unittest.TestCase):
    def test_home_becomes_a_tilde(self):
        self.assertEqual(dashboard._short_dir(str(os.path.expanduser("~")) + "/dev/x"),
                         "~/dev/x")

    def test_other_paths_are_absolute(self):
        self.assertEqual(dashboard._short_dir("/tmp/x"), "/tmp/x")

    def test_none(self):
        self.assertEqual(dashboard._short_dir(None), "")


if __name__ == "__main__":
    unittest.main()
