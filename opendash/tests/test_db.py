"""Level 2: snapshot() against a stand-in opencode database.

This is where the dashboard's whole notion of what an agent is doing comes
from, so each state gets pinned down with the rows that should produce it.
"""
from __future__ import annotations

import json
import unittest

from support import SandboxCase, now_ms


class States(SandboxCase):
    server_started = 0            # every message is newer than the "server"

    def snap(self):
        return self.ocore.snapshot(self.ocore.instance_records())[0]

    def test_a_finished_assistant_message_is_idle(self):
        self.box.record()
        self.box.session()
        self.box.message(role="user")
        self.box.message(role="assistant", completed=True)
        self.assertEqual(self.snap()["state"], "idle")

    def test_an_unfinished_assistant_message_is_working(self):
        self.box.record()
        self.box.session()
        self.box.message(role="assistant", completed=False)
        self.assertEqual(self.snap()["state"], "working")

    def test_a_trailing_user_message_is_queued(self):
        self.box.record()
        self.box.session()
        self.box.message(role="user")
        self.assertEqual(self.snap()["state"], "queued")

    def test_an_error_on_the_message_is_an_error(self):
        self.box.record()
        self.box.session()
        self.box.message(role="assistant", error="ProviderAuthError")
        item = self.snap()
        self.assertEqual(item["state"], "error")
        self.assertIn("ProviderAuthError", item["error"])

    def test_no_messages_yet_is_queued_inside_the_grace_period(self):
        self.box.record(created=now_ms())
        self.box.session()
        self.assertEqual(self.snap()["state"], "queued")

    def test_no_messages_after_the_grace_period_is_a_failed_launch(self):
        self.box.record(created=now_ms() - self.ocore.LAUNCH_GRACE_MS - 5_000)
        self.box.session()
        item = self.snap()
        self.assertEqual(item["state"], "error")
        self.assertIn("never started", item["error"])

    def test_a_session_that_no_longer_exists_is_gone(self):
        self.box.record()                      # no session row at all
        self.assertEqual(self.snap()["state"], "unknown")


class InterruptedRuns(SandboxCase):
    """A run belongs to the process that started it."""

    def test_an_unfinished_message_older_than_the_server_was_killed_with_it(self):
        self.box = type(self.box)(server_started=now_ms())      # server started now
        self.ocore = self.box.apply()
        self.box.record()
        self.box.session()
        self.box.message(role="assistant", completed=False, when=now_ms() - 60_000)
        item = self.ocore.snapshot(self.ocore.instance_records())[0]
        self.assertEqual(item["state"], "error")
        self.assertIn("interrupted", item["error"])

    def test_an_unfinished_message_newer_than_the_server_really_is_running(self):
        self.box = type(self.box)(server_started=now_ms() - 60_000)
        self.ocore = self.box.apply()
        self.box.record()
        self.box.session()
        self.box.message(role="assistant", completed=False, when=now_ms())
        self.assertEqual(
            self.ocore.snapshot(self.ocore.instance_records())[0]["state"], "working")


class Activity(SandboxCase):
    server_started = 0

    def snap(self):
        return self.ocore.snapshot(self.ocore.instance_records())[0]

    def test_a_running_tool_is_reported_with_its_target(self):
        self.box.record()
        self.box.session()
        mid = self.box.message(role="assistant", completed=False)
        self.box.part(mid, type="tool", tool="bash",
                      state={"status": "running", "input": {"command": "npm test"}})
        item = self.snap()
        self.assertEqual(item["activity"][0], "running")
        self.assertIn("npm test", item["activity"][1])

    def test_the_last_thing_said_is_used_when_idle(self):
        self.box.record()
        self.box.session()
        mid = self.box.message(role="assistant", completed=True)
        self.box.part(mid, type="text", text="Done. Added the retry.")
        item = self.snap()
        self.assertEqual(item["activity"], ("said", "Done. Added the retry."))

    def test_the_users_own_prompt_is_never_mistaken_for_output(self):
        self.box.record()
        self.box.session()
        user = self.box.message(role="user")
        self.box.part(user, type="text", text="THE PROMPT")
        self.assertEqual(self.snap()["activity"], ("none", ""))

    def test_file_tools_are_shown_by_basename(self):
        self.box.record()
        self.box.session()
        mid = self.box.message(role="assistant", completed=True)
        self.box.part(mid, type="tool", tool="edit",
                      state={"status": "completed", "input": {"filePath": "/a/b/Payment.java"}})
        self.assertEqual(self.snap()["activity"], ("tool", "edit Payment.java"))


class Todos(SandboxCase):
    server_started = 0

    def test_todos_are_read_in_order_and_counted(self):
        self.box.record()
        self.box.session()
        for i, (content, status) in enumerate([("audit", "completed"),
                                              ("fix", "in_progress"),
                                              ("verify", "pending")]):
            self.box.todo(content, status, i)
        item = self.ocore.snapshot(self.ocore.instance_records())[0]
        self.assertEqual([t["content"] for t in item["todos"]], ["audit", "fix", "verify"])
        self.assertEqual(self.ocore._progress(item), "✓1/3")


class Records(SandboxCase):
    def test_a_broken_record_is_skipped_rather_than_crashing(self):
        self.box.record(session_id="ses_good")
        (self.box.state / "instances" / "ses_bad.json").write_text("{not json")
        ids = [r["session_id"] for r in self.ocore.instance_records()]
        self.assertEqual(ids, ["ses_good"])

    def test_a_missing_database_degrades_instead_of_raising(self):
        self.box.record()
        self.box.db.unlink()
        item = self.ocore.snapshot(self.ocore.instance_records())[0]
        self.assertEqual(item["state"], "unknown")


class Reordering(SandboxCase):
    def test_moving_down_swaps_with_the_neighbour_and_persists(self):
        self.box.record(session_id="ses_a", created=100)
        self.box.record(session_id="ses_b", created=200)
        self.assertTrue(self.ocore.move_instance("ses_a", 1))
        order = [r["session_id"] for r in
                 self.ocore.sort_items(self.ocore.instance_records())]
        self.assertEqual(order, ["ses_b", "ses_a"])
        # and it survives a reload, because it lives in the record
        stored = json.loads((self.box.state / "instances" / "ses_a.json").read_text())
        self.assertIn("order", stored)

    def test_moving_past_the_end_does_nothing(self):
        self.box.record(session_id="ses_a", created=100)
        self.assertFalse(self.ocore.move_instance("ses_a", 1))
        self.assertFalse(self.ocore.move_instance("ses_a", -1))

    def test_an_unknown_instance_cannot_move(self):
        self.assertFalse(self.ocore.move_instance("ses_nope", 1))


class Renaming(SandboxCase):
    def test_the_name_is_stored_and_wins_over_the_generated_title(self):
        self.box.record()
        self.box.session(title="generated title")
        self.ocore.rename_instance("ses_test0001", "  my   name  ")
        item = self.ocore.snapshot(self.ocore.instance_records())[0]
        self.assertEqual(self.ocore._headline(item), "my name")

    def test_an_empty_name_is_ignored(self):
        rec = self.box.record()
        self.ocore.rename_instance(rec["session_id"], "   ")
        stored = json.loads(
            (self.box.state / "instances" / f"{rec['session_id']}.json").read_text())
        self.assertIsNone(stored.get("title_override"))


if __name__ == "__main__":
    unittest.main()
