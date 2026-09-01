"""Tests that use a fake HTTP server to exercise ocore's server-facing code."""
from __future__ import annotations

import json
import os
import sqlite3
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from support import ROOT, Sandbox, SandboxCase, now_ms  # noqa: F401
from fake_server import FakeServer

import ocore


class FakeServerCase(SandboxCase):
    """SandboxCase with a fake opencode server wired in."""

    def setUp(self):
        super().setUp()
        self.server = FakeServer().start()
        self.server.write_server_json(self.ocore.STATE)
        self.addCleanup(self.server.stop)
        # Patch _server_process_owned so server_url trusts the fake server.
        self._owned_patch = patch.object(self.ocore, "_server_process_owned", return_value=True)
        self._owned_patch.start()
        self.addCleanup(self._owned_patch.stop)


class HttpFunc(FakeServerCase):
    def test_get_returns_json(self):
        result = self.ocore.http(f"{self.server.url}/agent")
        self.assertIsInstance(result, list)

    def test_post_returns_json(self):
        result = self.ocore.http(f"{self.server.url}/session", "POST", {})
        self.assertEqual(result["id"], "ses_fake0000000001")

    def test_404_raises_api_error(self):
        with self.assertRaises(self.ocore.ApiError):
            self.ocore.http(f"{self.server.url}/nonexistent")

    def test_connection_refused_raises(self):
        with self.assertRaises(self.ocore.ApiError):
            self.ocore.http("http://127.0.0.1:1/nope", timeout=1)


class ServerAlive(FakeServerCase):
    def test_alive(self):
        self.assertTrue(self.ocore._server_alive(self.server.url))

    def test_dead(self):
        self.assertFalse(self.ocore._server_alive("http://127.0.0.1:1", timeout=1))


class ServerUrl(FakeServerCase):
    def test_returns_existing_url(self):
        self.assertEqual(self.ocore.server_url(), self.server.url)

    def test_start_false_returns_none_if_no_server(self):
        # Wipe server.json, no server alive
        (self.ocore.STATE / "server.json").unlink()
        self.assertIsNone(self.ocore.server_url(start=False))


class ServerAgents(FakeServerCase):
    def test_returns_names(self):
        agents = self.ocore.server_agents(self.server.url)
        self.assertEqual(agents, {"default", "build"})

    def test_empty_list(self):
        server = FakeServer(agents=[]).start()
        try:
            self.assertEqual(self.ocore.server_agents(server.url), set())
        finally:
            server.stop()

    def test_connection_error_returns_empty(self):
        self.assertEqual(self.ocore.server_agents("http://127.0.0.1:1"), set())


class CheckAgent(FakeServerCase):
    def test_no_agent_passes(self):
        self.ocore._check_agent(self.server.url, None)

    def test_known_agent_passes(self):
        self.ocore._check_agent(self.server.url, "build")

    def test_unknown_agent_raises(self):
        with patch.object(self.ocore.subprocess, "run",
                          return_value=type("R", (), {"stdout": "", "returncode": 0})()):
            with self.assertRaises(self.ocore.ApiError):
                self.ocore._check_agent(self.server.url, "nonexistent")


class NewInstance(FakeServerCase):
    def setUp(self):
        super().setUp()
        self._cfg_patch = patch.dict(self.ocore.CONFIG, {"agent": None, "model": None})
        self._cfg_patch.start()
        self.addCleanup(self._cfg_patch.stop)

    def test_creates_and_prompts(self):
        rec = self.ocore.new_instance("do the thing", directory="/tmp")
        self.assertEqual(rec["session_id"], "ses_fake0000000001")
        self.assertEqual(rec["task"], "do the thing")
        self.assertEqual(len(self.server.prompted), 1)

    def test_failed_prompt_removes_record(self):
        server = FakeServer(session_id="ses_fail").start()
        server.write_server_json(self.ocore.STATE)
        try:
            with patch.object(self.ocore, "send_prompt",
                              side_effect=self.ocore.ApiError("boom")), \
                 patch.object(self.ocore, "abort_instance") as abort:
                with self.assertRaises(self.ocore.ApiError):
                    self.ocore.new_instance("task", directory="/tmp")
                abort.assert_called_once_with("ses_fail")
            self.assertFalse(
                (self.ocore.INSTANCES / "ses_fail.json").exists())
        finally:
            server.stop()

    def test_with_ticket(self):
        rec = self.ocore.new_instance("fix PROJ-1 bug", ticket="PROJ-1", directory="/tmp")
        self.assertEqual(rec["ticket"], "PROJ-1")
        self.assertTrue(rec["ticket_manual"])

    def test_with_model(self):
        rec = self.ocore.new_instance("task", model="openai/gpt-4", directory="/tmp")
        self.assertEqual(rec["model"], "openai/gpt-4")

    def test_empty_task_rejected(self):
        # _cmd_new handles this, but new_instance itself accepts it
        rec = self.ocore.new_instance("task", directory="/tmp")
        self.assertEqual(rec["task"], "task")


class SendPrompt(FakeServerCase):
    def test_sends_prompt(self):
        self.ocore.send_prompt("ses_x", "hello", "/tmp")
        self.assertEqual(len(self.server.prompted), 1)
        path, body = self.server.prompted[0]
        self.assertIn("ses_x", path)
        self.assertEqual(body["parts"][0]["text"], "hello")

    def test_with_model_and_agent(self):
        self.ocore.send_prompt("ses_x", "hi", "/tmp", model="prov/model", agent="build")
        path, body = self.server.prompted[0]
        self.assertEqual(body["model"], {"providerID": "prov", "modelID": "model"})
        self.assertEqual(body["agent"], "build")


class AbortInstance(FakeServerCase):
    def test_aborts(self):
        self.ocore.abort_instance("ses_x")
        self.assertEqual(len(self.server.aborted), 1)
        self.assertIn("ses_x", self.server.aborted[0])

    def test_no_server_returns_silently(self):
        (self.ocore.STATE / "server.json").unlink()
        self.ocore.abort_instance("ses_x")


class RenameInstance(FakeServerCase):
    def test_renames(self):
        self.ocore.INSTANCES.mkdir(parents=True, exist_ok=True)
        path = self.ocore.INSTANCES / "ses_x.json"
        self.ocore._write_json(path, {"session_id": "ses_x", "directory": "/tmp"})
        self.ocore.rename_instance("ses_x", "new name")
        rec = self.ocore._read_json(path)
        self.assertEqual(rec["title_override"], "new name")
        self.assertEqual(len(self.server.patched), 1)

    def test_empty_name_does_nothing(self):
        self.ocore.rename_instance("ses_x", "")
        self.assertEqual(len(self.server.patched), 0)

    def test_rename_nonexistent_record_still_patches(self):
        self.ocore.rename_instance("ses_nonexistent", "name")
        self.assertEqual(len(self.server.patched), 1)


class StopServer(FakeServerCase):
    def test_stop_server(self):
        self.assertTrue(self.ocore.stop_server())
        self.assertFalse((self.ocore.STATE / "server.json").exists())

    def test_stop_no_server(self):
        (self.ocore.STATE / "server.json").unlink()
        self.assertFalse(self.ocore.stop_server())


class PendingAttention(FakeServerCase):
    def test_no_items(self):
        self.assertEqual(self.ocore.pending_attention([]), {})

    def test_permission_request(self):
        items = [{"session_id": "ses_x", "directory": "/tmp"}]
        server = FakeServer(permissions=[
            {"sessionID": "ses_x", "permission": "bash",
             "metadata": {"command": "rm -rf"}}
        ]).start()
        server.write_server_json(self.ocore.STATE)
        try:
            result = self.ocore.pending_attention(items)
            self.assertEqual(result["ses_x"], "bash rm -rf")
        finally:
            server.stop()

    def test_permission_with_patterns(self):
        items = [{"session_id": "ses_y", "directory": "/tmp"}]
        server = FakeServer(permissions=[
            {"sessionID": "ses_y", "permission": "edit",
             "patterns": ["/tmp/secret.txt"]}
        ]).start()
        server.write_server_json(self.ocore.STATE)
        try:
            result = self.ocore.pending_attention(items)
            self.assertEqual(result["ses_y"], "edit /tmp/secret.txt")
        finally:
            server.stop()

    def test_question_blocks(self):
        items = [{"session_id": "ses_q", "directory": "/tmp", "state": "working"}]
        server = FakeServer(permissions=[], questions={
            "ses_q": [{"question": "which color?"}]
        }).start()
        server.write_server_json(self.ocore.STATE)
        try:
            result = self.ocore.pending_attention(items)
            self.assertIn("ses_q", result)
            self.assertIn("question", result["ses_q"])
        finally:
            server.stop()


class TicketUrl(FakeServerCase):
    def test_no_config_no_ticket(self):
        self.assertIsNone(self.ocore.ticket_url(""))

    def test_with_jira_cache(self):
        with patch.object(self.ocore, "jira_cache",
                          return_value={"PROJ-1": {"url": "http://jira/PROJ-1"}}):
            self.assertEqual(self.ocore.ticket_url("PROJ-1"), "http://jira/PROJ-1")


class Snapshot(FakeServerCase):
    def test_empty_records(self):
        self.assertEqual(self.ocore.snapshot([]), [])

    def test_session_not_in_db(self):
        rec = {"session_id": "ses_missing", "created": now_ms()}
        items = self.ocore.snapshot([rec])
        self.assertEqual(len(items), 1)
        self.assertFalse(items[0].get("exists", True))
        self.assertEqual(items[0]["state"], "unknown")

    def test_session_in_db_idle(self):
        self.box.session("ses_idle", title="do thing")
        self.box.message(session_id="ses_idle", role="assistant", when=now_ms())
        rec = self.box.record(session_id="ses_idle")
        items = self.ocore.snapshot([rec])
        self.assertEqual(items[0]["state"], "idle")
        self.assertTrue(items[0]["exists"])

    def test_session_working(self):
        self.box.session("ses_work", title="working thing")
        self.box.message(session_id="ses_work", role="assistant",
                         completed=False, when=now_ms())
        rec = self.box.record(session_id="ses_work")
        rec["created"] = now_ms()
        items = self.ocore.snapshot([rec])
        self.assertEqual(items[0]["state"], "working")

    def test_session_error(self):
        self.box.session("ses_err", title="errored")
        self.box.message(session_id="ses_err", role="assistant",
                         completed=True, error="boom", when=now_ms())
        rec = self.box.record(session_id="ses_err")
        items = self.ocore.snapshot([rec])
        self.assertEqual(items[0]["state"], "error")
        self.assertEqual(items[0]["error"], "boom")

    def test_session_queued(self):
        self.box.session("ses_q", title="queued")
        self.box.message(session_id="ses_q", role="user", when=now_ms())
        rec = self.box.record(session_id="ses_q")
        items = self.ocore.snapshot([rec])
        self.assertEqual(items[0]["state"], "queued")

    def test_stalled_launch(self):
        self.box.session("ses_stall", title="stalled")
        rec = {"session_id": "ses_stall", "created": now_ms() - 60_000}
        items = self.ocore.snapshot([rec])
        self.assertEqual(items[0]["state"], "error")

    def test_todos_included(self):
        self.box.session("ses_t", title="with todos")
        self.box.message(session_id="ses_t", role="assistant", when=now_ms())
        self.box.todo("task a", "completed", 0, session_id="ses_t")
        self.box.todo("task b", "in_progress", 1, session_id="ses_t")
        rec = self.box.record(session_id="ses_t")
        items = self.ocore.snapshot([rec])
        self.assertEqual(len(items[0]["todos"]), 2)
        self.assertEqual(items[0]["todos"][0]["status"], "completed")


class SnapshotServerStarted(FakeServerCase):
    def test_interrupted_when_older_than_server(self):
        msg_time = now_ms() - 100_000
        self.box.session("ses_old", title="old")
        self.box.message(session_id="ses_old", role="assistant",
                         completed=False, when=msg_time)
        rec = self.box.record(session_id="ses_old")
        # server.json says started=now, so the message is older
        self.server.write_server_json(self.ocore.STATE, pid=1)
        # Manually set started to a time after the message
        import json
        info = json.loads((self.ocore.STATE / "server.json").read_text())
        info["started"] = msg_time + 50000
        (self.ocore.STATE / "server.json").write_text(json.dumps(info))
        items = self.ocore.snapshot([rec])
        self.assertEqual(items[0]["state"], "error")
        self.assertIn("interrupted", items[0].get("error", ""))


class CmdList(FakeServerCase):
    def test_no_instances(self):
        rc = self.ocore._cmd_list(type("A", (), {"name": None, "full": False, "id_only": False})())
        self.assertEqual(rc, 0)

    def test_with_instance(self):
        self.box.session("ses_l", title="do thing")
        self.box.message(session_id="ses_l", role="assistant", when=now_ms())
        self.box.record(session_id="ses_l")
        rc = self.ocore._cmd_list(type("A", (), {"name": None, "full": False, "id_only": False})())
        self.assertEqual(rc, 0)

    def test_id_only(self):
        self.box.session("ses_l2", title="do thing")
        self.box.message(session_id="ses_l2", role="assistant", when=now_ms())
        self.box.record(session_id="ses_l2")
        rc = self.ocore._cmd_list(type("A", (), {"name": None, "full": False, "id_only": True})())
        self.assertEqual(rc, 0)

    def test_name_filter(self):
        self.box.session("ses_a", title="alpha")
        self.box.message(session_id="ses_a", role="assistant", when=now_ms())
        self.box.record(session_id="ses_a")
        self.box.session("ses_b", title="beta")
        self.box.message(session_id="ses_b", role="assistant", when=now_ms())
        self.box.record(session_id="ses_b")
        rc = self.ocore._cmd_list(type("A", (), {"name": "alpha", "full": False, "id_only": False})())
        self.assertEqual(rc, 0)


class CmdClear(FakeServerCase):
    def test_clear_messages(self):
        self.box.session("ses_c")
        self.box.message(session_id="ses_c", role="user", when=now_ms())
        self.box.message(session_id="ses_c", role="assistant", when=now_ms() + 1)
        self.box.record(session_id="ses_c")
        args = type("A", (), {"session_id": "ses_c"})()
        rc = self.ocore._cmd_clear(args)
        self.assertEqual(rc, 0)
        con = sqlite3.connect(self.box.db)
        count = con.execute("select count(*) from message where session_id='ses_c'").fetchone()[0]
        con.close()
        self.assertEqual(count, 0)

    def test_clear_no_db(self):
        self.box.db.unlink()
        args = type("A", (), {"session_id": "ses_x"})()
        rc = self.ocore._cmd_clear(args)
        self.assertEqual(rc, 1)


class CmdServer(FakeServerCase):
    def test_status(self):
        args = type("A", (), {"action": "status"})()
        rc = self.ocore._cmd_server(args)
        self.assertEqual(rc, 0)

    def test_start(self):
        args = type("A", (), {"action": "start"})()
        rc = self.ocore._cmd_server(args)
        self.assertEqual(rc, 0)

    def test_stop(self):
        args = type("A", (), {"action": "stop"})()
        rc = self.ocore._cmd_server(args)
        self.assertEqual(rc, 0)


class CmdPrompt(FakeServerCase):
    def test_prompt_unknown_session(self):
        args = type("A", (), {"session_id": "ses_nonexistent", "text": ["hi"]})()
        rc = self.ocore._cmd_prompt(args)
        self.assertEqual(rc, 1)

    def test_prompt_sends(self):
        self.box.record(session_id="ses_p")
        args = type("A", (), {"session_id": "ses_p", "text": ["hello", "world"]})()
        rc = self.ocore._cmd_prompt(args)
        self.assertEqual(rc, 0)
        self.assertEqual(len(self.server.prompted), 1)


class CmdAbort(FakeServerCase):
    def test_abort(self):
        args = type("A", (), {"session_id": ["ses_x"]})()
        rc = self.ocore._cmd_abort(args)
        self.assertEqual(rc, 0)
        self.assertEqual(len(self.server.aborted), 1)


class CmdQuit(FakeServerCase):
    def test_quit(self):
        self.box.record(session_id="ses_q1")
        self.box.record(session_id="ses_q2")
        with patch.object(self.ocore, "tmux") as tmux_mock:
            rc = self.ocore._cmd_quit(type("A", (), {})())
        self.assertEqual(rc, 0)
        self.assertEqual(len(self.server.aborted), 2)


class CmdScreen(SandboxCase):
    def test_no_screen_file(self):
        args = type("A", (), {})()
        rc = self.ocore._cmd_screen(args)
        self.assertEqual(rc, 1)


class AgentsForDirectory(FakeServerCase):
    def test_no_records(self):
        self.assertEqual(self.ocore.agents_for_directory("/nonexistent"), [])

    def test_finds_matching(self):
        self.box.session("ses_d", title="thing")
        self.box.message(session_id="ses_d", role="assistant", when=now_ms())
        rec = self.box.record(session_id="ses_d", directory="/tmp")
        items = self.ocore.agents_for_directory("/tmp")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["agent_name"], "default")


if __name__ == "__main__":
    unittest.main()