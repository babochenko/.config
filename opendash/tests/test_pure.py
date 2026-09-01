"""Tests for pure functions in ocore.py that need no server, tmux, or git."""
from __future__ import annotations

import json
import time
import unittest

from support import ROOT  # noqa: F401  (puts opendash on sys.path)

import ocore


class ToolTarget(unittest.TestCase):
    def test_plain_tool_name(self):
        self.assertEqual(ocore._tool_target("bash", {}), "bash")

    def test_file_path_is_shortened(self):
        inp = {"filePath": "/long/path/to/src/main.py"}
        self.assertEqual(ocore._tool_target("edit", inp), "edit main.py")

    def test_command_is_truncated(self):
        inp = {"command": "npm test -- --grep 'a very long pattern that exceeds the limit'"}
        out = ocore._tool_target("bash", inp)
        self.assertTrue(out.startswith("bash "))
        self.assertLessEqual(len(out), 65)

    def test_query_field(self):
        self.assertEqual(ocore._tool_target("search", {"query": "foo"}), "search foo")

    def test_url_field(self):
        self.assertEqual(ocore._tool_target("fetch", {"url": "http://x"}), "fetch http://x")

    def test_pattern_field(self):
        self.assertEqual(ocore._tool_target("grep", {"pattern": "abc"}), "grep abc")

    def test_non_dict_input(self):
        self.assertEqual(ocore._tool_target("tool", "not a dict"), "tool")


class Activity(unittest.TestCase):
    def _part(self, ptype, **kwargs):
        d = {"type": ptype, **kwargs}
        return (json.dumps(d), int(time.time() * 1000))

    def test_running_tool(self):
        parts = [self._part("tool", tool="bash", state={"status": "running", "input": {"command": "npm test"}})]
        self.assertEqual(ocore._activity(parts), ("running", "bash npm test"))

    def test_completed_tool_then_text(self):
        parts = [
            self._part("text", text="first line\nsecond line"),
            self._part("tool", tool="edit", state={"status": "completed", "input": {"filePath": "a.py"}}),
        ]
        kind, text = ocore._activity(parts)
        self.assertEqual(kind, "said")
        self.assertEqual(text, "first line")

    def test_only_completed_tools(self):
        parts = [self._part("tool", tool="read", state={"status": "completed", "input": {"filePath": "x.py"}})]
        kind, text = ocore._activity(parts)
        self.assertEqual(kind, "tool")
        self.assertEqual(text, "read x.py")

    def test_empty_parts(self):
        self.assertEqual(ocore._activity([]), ("none", ""))

    def test_pending_tool_is_running(self):
        parts = [self._part("tool", tool="bash", state={"status": "pending", "input": {"command": "ls"}})]
        self.assertEqual(ocore._activity(parts), ("running", "bash ls"))

    def test_text_with_no_content(self):
        parts = [self._part("text", text=""), self._part("tool", tool="ls", state={"status": "completed"})]
        kind, text = ocore._activity(parts)
        self.assertEqual(kind, "tool")


class IsShellName(unittest.TestCase):
    def test_known_shells(self):
        for name in ("sh", "bash", "zsh", "dash", "ksh", "fish", "csh", "tcsh"):
            self.assertTrue(ocore._is_shell_name(name))

    def test_ends_with_sh(self):
        self.assertTrue(ocore._is_shell_name("pwsh"))
        self.assertTrue(ocore._is_shell_name("/bin/sh"))

    def test_not_a_shell(self):
        self.assertFalse(ocore._is_shell_name("python"))
        self.assertFalse(ocore._is_shell_name("node"))


class TypedCommand(unittest.TestCase):
    def test_strips_shell_prefix(self):
        self.assertEqual(ocore._typed_command("/bin/sh ./gradlew test"), "gradlew test")

    def test_keeps_non_shell(self):
        self.assertEqual(ocore._typed_command("python script.py"), "python script.py")

    def test_empty(self):
        self.assertEqual(ocore._typed_command(""), "")


class StripTicket(unittest.TestCase):
    def test_strips_prefix(self):
        self.assertEqual(ocore._strip_ticket("PROJ-123 do the thing", "PROJ-123"), "do the thing")

    def test_strips_separators(self):
        self.assertEqual(ocore._strip_ticket("PROJ-123: do the thing", "PROJ-123"), "do the thing")
        self.assertEqual(ocore._strip_ticket("PROJ-123 - do the thing", "PROJ-123"), "do the thing")

    def test_no_ticket(self):
        self.assertEqual(ocore._strip_ticket("do the thing", None), "do the thing")

    def test_ticket_not_at_start(self):
        self.assertEqual(ocore._strip_ticket("fix PROJ-123 now", "PROJ-123"), "fix PROJ-123 now")


class Headline(unittest.TestCase):
    def test_title_override_wins(self):
        item = {"title_override": "my name", "title": "generated", "task": "original task"}
        self.assertEqual(ocore._headline(item), "my name")

    def test_generated_title(self):
        item = {"title": "fix the bug", "task": "do the thing"}
        self.assertEqual(ocore._headline(item), "fix the bug")

    def test_idle_title_falls_through_in_snapshot_not_headline(self):
        item = {"title": "New session - 2026-01-01T00:00:00.000Z", "task": "do the thing"}
        self.assertEqual(ocore._headline(item), "New session - 2026-01-01T00:00:00.000Z")

    def test_falls_back_to_task(self):
        item = {"task": "do the thing\nsecond line"}
        self.assertEqual(ocore._headline(item), "do the thing")

    def test_strips_ticket_from_title(self):
        item = {"title": "PROJ-123 fix the bug", "ticket": "PROJ-123"}
        self.assertEqual(ocore._headline(item), "fix the bug")

    def test_no_task(self):
        item = {}
        self.assertEqual(ocore._headline(item), "(no task)")


class Progress(unittest.TestCase):
    def test_no_todos(self):
        self.assertEqual(ocore._progress({}), "")

    def test_some_done(self):
        item = {"todos": [
            {"status": "completed", "content": "a"},
            {"status": "completed", "content": "b"},
            {"status": "in_progress", "content": "c"},
        ]}
        self.assertEqual(ocore._progress(item), "✓2/3")


class WorkedOn(unittest.TestCase):
    def test_working_with_running_tool(self):
        item = {"state": "working", "activity": ("running", "npm test"), "todos": []}
        self.assertEqual(ocore.worked_on(item), "npm test")

    def test_working_with_current_todo_and_running(self):
        item = {"state": "working", "activity": ("running", "npm test"),
                "todos": [{"status": "in_progress", "content": "fix tests"}]}
        self.assertEqual(ocore.worked_on(item), "fix tests — npm test")

    def test_working_thinking(self):
        item = {"state": "working", "activity": ("none", ""), "todos": []}
        self.assertEqual(ocore.worked_on(item), "thinking…")

    def test_error(self):
        item = {"state": "error", "error": "something broke"}
        self.assertEqual(ocore.worked_on(item), "something broke")

    def test_queued(self):
        item = {"state": "queued"}
        self.assertEqual(ocore.worked_on(item), "queued — waiting for the model")

    def test_idle_with_said(self):
        item = {"state": "idle", "activity": ("said", "done!"), "todos": []}
        self.assertEqual(ocore.worked_on(item), "done!")

    def test_idle_no_output(self):
        item = {"state": "idle", "activity": ("none", ""), "todos": []}
        self.assertEqual(ocore.worked_on(item), "no output yet")


class FmtAge(unittest.TestCase):
    def test_zero(self):
        self.assertEqual(ocore.fmt_age(0), "")

    def test_none(self):
        self.assertEqual(ocore.fmt_age(None), "")

    def test_seconds(self):
        ms = int((time.time() - 5) * 1000)
        self.assertEqual(ocore.fmt_age(ms), "5s")

    def test_minutes(self):
        ms = int((time.time() - 120) * 1000)
        self.assertEqual(ocore.fmt_age(ms), "2m")

    def test_hours(self):
        ms = int((time.time() - 3661) * 1000)
        self.assertEqual(ocore.fmt_age(ms), "1h01")


class SplitModel(unittest.TestCase):
    def test_with_slash(self):
        self.assertEqual(ocore._split_model("openai/gpt-4"),
                         {"providerID": "openai", "modelID": "gpt-4"})

    def test_no_slash(self):
        self.assertIsNone(ocore._split_model("gpt-4"))

    def test_none(self):
        self.assertIsNone(ocore._split_model(None))


class DisplayAgent(unittest.TestCase):
    def test_title_override(self):
        self.assertEqual(ocore.display_agent({"title_override": "custom"}), "custom")

    def test_agent_live(self):
        self.assertEqual(ocore.display_agent({"agent_live": "live"}), "live")

    def test_agent(self):
        self.assertEqual(ocore.display_agent({"agent": "build"}), "build")

    def test_default(self):
        self.assertEqual(ocore.display_agent({}), "default")


class OrderKey(unittest.TestCase):
    def test_explicit_order(self):
        self.assertEqual(ocore.order_key({"order": 5}), 5.0)

    def test_created(self):
        self.assertEqual(ocore.order_key({"created": 1000}), 1000.0)

    def test_time_created(self):
        self.assertEqual(ocore.order_key({"time_created": 2000}), 2000.0)

    def test_zero(self):
        self.assertEqual(ocore.order_key({}), 0.0)


class SortItems(unittest.TestCase):
    def test_sorts_by_order(self):
        items = [{"session_id": "b", "created": 2}, {"session_id": "a", "created": 1}]
        result = ocore.sort_items(items)
        self.assertEqual(result[0]["session_id"], "a")

    def test_respects_manual_order(self):
        items = [{"session_id": "b", "order": 1}, {"session_id": "a", "order": 2}]
        result = ocore.sort_items(items)
        self.assertEqual(result[0]["session_id"], "b")


class ShQuote(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(ocore._sh_quote("hello"), "'hello'")

    def test_with_single_quote(self):
        self.assertEqual(ocore._sh_quote("it's"), "'it'\\''s'")


class GitFail(unittest.TestCase):
    def test_with_stderr(self):
        result = type("R", (), {"stderr": "fatal: bad ref", "stdout": ""})()
        err = ocore._git_fail(result, "worktree add")
        self.assertIn("worktree add", str(err))
        self.assertIn("bad ref", str(err))


class Label(unittest.TestCase):
    def test_with_ticket(self):
        item = {"ticket": "PROJ-1", "title": "do thing"}
        label = ocore._label(item)
        self.assertIn("PROJ-1", label)
        self.assertIn("do thing", label)

    def test_no_ticket(self):
        item = {"title": "do thing"}
        self.assertIn("do thing", ocore._label(item))


class PermissionJson(unittest.TestCase):
    def test_custom_json(self):
        import os
        os.environ["OPENDASH_PERMISSION"] = '{"read":"ask"}'
        try:
            self.assertEqual(json.loads(ocore.permission_json()), {"read": "ask"})
        finally:
            del os.environ["OPENDASH_PERMISSION"]

    def test_invalid_json(self):
        import os
        os.environ["OPENDASH_PERMISSION"] = "not json"
        try:
            with self.assertRaises(ocore.ApiError):
                ocore.permission_json()
        finally:
            del os.environ["OPENDASH_PERMISSION"]

    def test_non_object(self):
        import os
        os.environ["OPENDASH_PERMISSION"] = "[1,2]"
        try:
            with self.assertRaises(ocore.ApiError):
                ocore.permission_json()
        finally:
            del os.environ["OPENDASH_PERMISSION"]


if __name__ == "__main__":
    unittest.main()