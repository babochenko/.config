"""Tests for sandbox-backed ocore functions and metadata/dashboard pure functions."""
from __future__ import annotations

import json
import sqlite3
import time
import unittest
from pathlib import Path

from support import ROOT, Sandbox, SandboxCase, now_ms  # noqa: F401

import metadata


# ---------------------------------------------------------------- ocore sandbox

class PruneMessages(SandboxCase):
    def test_prune_keeps_last_n(self):
        self.box.session("ses_A")
        ids = []
        for i in range(35):
            ids.append(self.box.message(session_id="ses_A", message_id=f"msg_{i:02d}", when=now_ms() + i))
        self.ocore.prune_session_messages("ses_A", keep=10)
        con = sqlite3.connect(self.box.db)
        remaining = con.execute("select count(*) from message where session_id='ses_A'").fetchone()[0]
        con.close()
        self.assertEqual(remaining, 10)

    def test_prune_deletes_parts(self):
        self.box.session("ses_B")
        mid = self.box.message(session_id="ses_B", message_id="msg_keep", when=now_ms())
        old_mid = self.box.message(session_id="ses_B", message_id="msg_old", when=now_ms() - 100)
        self.box.part(mid, session_id="ses_B", text="keep")
        self.box.part(old_mid, session_id="ses_B", text="old")
        self.ocore.prune_session_messages("ses_B", keep=1)
        con = sqlite3.connect(self.box.db)
        parts = con.execute("select count(*) from part where session_id='ses_B'").fetchone()[0]
        con.close()
        self.assertEqual(parts, 1)

    def test_prune_no_messages(self):
        self.ocore.prune_session_messages("ses_nonexistent", keep=30)

    def test_prune_no_db(self):
        self.box.db.unlink()
        self.ocore.prune_session_messages("ses_X", keep=30)


class MetadataAgentRecord(SandboxCase):
    def test_no_session_file(self):
        self.assertIsNone(self.ocore.metadata_agent_sid())
        self.assertIsNone(self.ocore.metadata_agent_record())

    def test_with_session_file(self):
        (self.ocore.STATE / "metadata-agent-session.json").write_text(
            json.dumps({"id": "ses_meta123"}))
        sid = self.ocore.metadata_agent_sid()
        self.assertEqual(sid, "ses_meta123")
        rec = self.ocore.metadata_agent_record()
        self.assertEqual(rec["session_id"], "ses_meta123")
        self.assertTrue(rec["_metadata_agent"])
        self.assertEqual(rec["title_override"], "metadata agent")


class ResolveSessionId(SandboxCase):
    def test_fuzzy_metadata(self):
        (self.ocore.STATE / "metadata-agent-session.json").write_text(
            json.dumps({"id": "ses_meta456"}))
        self.box.session("ses_meta456")
        self.assertEqual(self.ocore._resolve_session_id("metadata"), "ses_meta456")

    def test_fuzzy_meta(self):
        (self.ocore.STATE / "metadata-agent-session.json").write_text(
            json.dumps({"id": "ses_meta789"}))
        self.box.session("ses_meta789")
        self.assertEqual(self.ocore._resolve_session_id("meta"), "ses_meta789")

    def test_direct_sid(self):
        self.assertEqual(self.ocore._resolve_session_id("ses_direct"), "ses_direct")

    def test_no_match(self):
        self.assertIsNone(self.ocore._resolve_session_id("nonexistent"))


class MoveInstance(SandboxCase):
    def test_move_down(self):
        self.box.record(session_id="ses_A", created=100)
        self.box.record(session_id="ses_B", created=200)
        self.assertTrue(self.ocore.move_instance("ses_A", 1))

    def test_move_up(self):
        self.box.record(session_id="ses_A", created=100)
        self.box.record(session_id="ses_B", created=200)
        self.assertTrue(self.ocore.move_instance("ses_B", -1))

    def test_move_at_boundary(self):
        self.box.record(session_id="ses_A", created=100)
        self.assertFalse(self.ocore.move_instance("ses_A", -1))
        self.assertFalse(self.ocore.move_instance("ses_A", 1))


class LatestAssistantResponse(SandboxCase):
    def test_returns_text_and_completed(self):
        self.box.session("ses_L")
        mid = self.box.message(session_id="ses_L", role="assistant", when=now_ms())
        self.box.part(mid, session_id="ses_L", text="hello world")
        result = self.ocore.latest_assistant_response("ses_L")
        self.assertIsNotNone(result)
        self.assertIn("hello world", result[0])
        self.assertTrue(result[1])

    def test_returns_none_for_no_messages(self):
        self.box.session("ses_L2")
        self.assertIsNone(self.ocore.latest_assistant_response("ses_L2"))

    def test_after_filter(self):
        self.box.session("ses_L3")
        t0 = now_ms()
        old_mid = self.box.message(session_id="ses_L3", role="assistant", when=t0)
        self.box.part(old_mid, session_id="ses_L3", text="old")
        new_mid = self.box.message(session_id="ses_L3", role="assistant", when=t0 + 100)
        self.box.part(new_mid, session_id="ses_L3", text="new")
        result = self.ocore.latest_assistant_response("ses_L3", after=t0 + 50)
        self.assertIsNotNone(result)
        self.assertIn("new", result[0])


class UnlinkLink(SandboxCase):
    def test_unlink_ticket(self):
        self.box.record(session_id="ses_U", ticket="PROJ-1")
        metadata.associate_ticket(self.ocore.STATE, "ses_U", "PROJ-1")
        self.assertTrue(self.ocore.unlink_association("ses_U", "PROJ-1"))

    def test_link_ticket(self):
        self.box.record(session_id="ses_LK")
        self.assertTrue(self.ocore.link_association("ses_LK", "PROJ-2"))


# ---------------------------------------------------------- metadata.py pure

class ExtractTickets(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(metadata.extract_tickets("see PROJ-123 for details"), ["PROJ-123"])

    def test_url(self):
        self.assertEqual(metadata.extract_tickets("https://jira/browse/ABC-456"), ["ABC-456"])

    def test_multiple_dedup(self):
        result = metadata.extract_tickets("PROJ-1 and PROJ-1 and PROJ-2")
        self.assertEqual(result, ["PROJ-1", "PROJ-2"])

    def test_empty(self):
        self.assertEqual(metadata.extract_tickets(""), [])

    def test_extract_ticket_single(self):
        self.assertEqual(metadata.extract_ticket("PROJ-1"), "PROJ-1")

    def test_extract_ticket_none(self):
        self.assertIsNone(metadata.extract_ticket("nothing here"))


class ExtractPRs(unittest.TestCase):
    def test_url(self):
        prs = metadata.extract_prs("see https://bitbucket.org/team/repo/pull-requests/42")
        self.assertEqual(len(prs), 1)
        self.assertEqual(prs[0]["number"], "42")

    def test_ref(self):
        prs = metadata.extract_prs("PR #99 needs review")
        self.assertEqual(len(prs), 1)
        self.assertEqual(prs[0]["number"], "99")

    def test_dedup(self):
        text = "https://bitbucket.org/t/r/pull-requests/5 and PR #5"
        prs = metadata.extract_prs(text)
        self.assertEqual(len(prs), 1)

    def test_empty(self):
        self.assertEqual(metadata.extract_prs(""), [])


class RepositoryFromPR(unittest.TestCase):
    def test_normal(self):
        url = "https://bitbucket.org/team/repo/pull-requests/42"
        self.assertEqual(metadata._repository_from_pr_url(url), "team/repo")

    def test_none(self):
        self.assertIsNone(metadata._repository_from_pr_url(None))
        self.assertIsNone(metadata._repository_from_pr_url(""))


class CandidateKey(unittest.TestCase):
    def test_with_repo(self):
        self.assertEqual(metadata._candidate_key({"repository": "team/r", "number": "42"}), "team/r#42")

    def test_no_repo(self):
        self.assertEqual(metadata._candidate_key({"number": "42"}), "#42")


class TextExtraction(unittest.TestCase):
    def test_dict_with_text(self):
        self.assertEqual(metadata._text({"text": "hello"}), ["hello"])

    def test_nested(self):
        d = {"parts": [{"text": "a"}, {"text": "b"}]}
        self.assertEqual(metadata._text(d), ["a", "b"])

    def test_list(self):
        self.assertEqual(metadata._text([{"text": "x"}, {"text": "y"}]), ["x", "y"])

    def test_plain_string(self):
        self.assertEqual(metadata._text("hello"), [])


class JsonResponse(unittest.TestCase):
    def test_valid_json(self):
        self.assertEqual(metadata._json_response('{"prs": []}'), {"prs": []})

    def test_json_in_prose(self):
        text = 'The result is {"prs": [{"number": "1"}]} and done'
        self.assertEqual(metadata._json_response(text), {"prs": [{"number": "1"}]})

    def test_no_json(self):
        self.assertIsNone(metadata._json_response("no json here"))

    def test_empty(self):
        self.assertIsNone(metadata._json_response(""))


class ParseAssociation(unittest.TestCase):
    def test_pr_url(self):
        self.assertEqual(metadata._parse_association("https://bitbucket.org/t/r/pull-requests/42"), "42")

    def test_hash_ref(self):
        self.assertEqual(metadata._parse_association("#99"), "99")

    def test_plain_number(self):
        self.assertEqual(metadata._parse_association("123"), "123")


class NormaliseTicket(unittest.TestCase):
    def test_simple(self):
        result = metadata._normalise_ticket({"status": "Done", "url": "http://x"}, "PROJ-1")
        self.assertEqual(result["key"], "PROJ-1")
        self.assertEqual(result["status"], "Done")
        self.assertEqual(result["url"], "http://x")

    def test_status_dict(self):
        result = metadata._normalise_ticket({"status": {"name": "In Progress"}}, "T-1")
        self.assertEqual(result["status"], "In Progress")

    def test_category_mapping(self):
        result = metadata._normalise_ticket({"status": "To Do"}, "T-2")
        self.assertEqual(result["category"], "todo")


class NormalisePRStatus(unittest.TestCase):
    def test_merged(self):
        self.assertEqual(metadata._normalise_pr_status({"state": "MERGED"}), "merged")

    def test_declined(self):
        self.assertEqual(metadata._normalise_pr_status({"state": "DECLINED"}), "rejected")

    def test_needs_changes(self):
        self.assertEqual(metadata._normalise_pr_status({"review_status": "needs_changes"}), "needs changes")

    def test_approved(self):
        self.assertEqual(metadata._normalise_pr_status({"review_status": "approved"}), "approved")

    def test_open(self):
        self.assertEqual(metadata._normalise_pr_status({"state": "OPEN"}), "opened")

    def test_unknown(self):
        self.assertIsNone(metadata._normalise_pr_status({}))


class NormalisePR(unittest.TestCase):
    def test_full(self):
        v = {"number": 42, "title": "Fix", "url": "http://x", "approvals": 2,
             "unresolved_threads": 1, "unresolved_comments": [{"id": 1}],
             "builds": {"ok": 3, "failed": 1, "unavailable": 0},
             "tickets": ["PROJ-1"]}
        result = metadata._normalise_pr(v, {"repository": "team/r", "number": "42"})
        self.assertEqual(result["number"], "42")
        self.assertEqual(result["label"], "#42")
        self.assertEqual(result["approvals"], 2)
        self.assertEqual(result["builds"]["ok"], 3)
        self.assertEqual(result["unresolved_threads"], 1)
        self.assertEqual(result["tickets"], ["PROJ-1"])


class McpConfig(unittest.TestCase):
    def test_defaults(self):
        import os
        old = os.environ.get("OPENDASH_CONFIG")
        os.environ["OPENDASH_CONFIG"] = "/nonexistent"
        try:
            cfg = metadata.mcp_config()
            self.assertEqual(cfg["tool"], "opendash_metadata")
            self.assertGreater(cfg["timeout"], 0)
        finally:
            if old is not None:
                os.environ["OPENDASH_CONFIG"] = old
            else:
                os.environ.pop("OPENDASH_CONFIG", None)


# ---------------------------------------------------------- dashboard.py pure

class Clip(unittest.TestCase):
    def test_fits(self):
        import dashboard
        self.assertEqual(dashboard.clip("hello", 10), "hello")

    def test_truncates(self):
        import dashboard
        self.assertEqual(dashboard.clip("hello world", 5), "hell…")

    def test_zero_width(self):
        import dashboard
        self.assertEqual(dashboard.clip("hello", 0), "")


class Width(unittest.TestCase):
    def test_ascii(self):
        import dashboard
        self.assertEqual(dashboard._w("a"), 1)

    def test_wide(self):
        import dashboard
        self.assertEqual(dashboard._w("あ"), 2)


class AnsiSegments(unittest.TestCase):
    def test_plain_text(self):
        import dashboard
        segments = dashboard._ansi_segments("hello world")
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0][0], "hello world")

    def test_color_codes(self):
        import dashboard
        text = "\x1b[32mgreen\x1b[0m plain"
        segments = dashboard._ansi_segments(text)
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0][0], "green")
        self.assertEqual(segments[1][0], " plain")


if __name__ == "__main__":
    unittest.main()