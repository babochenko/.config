import json
import io
import sys
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from support import ROOT  # noqa: F401  (puts opendash on sys.path)

import dashboard
import ocore


class DashboardTests(unittest.TestCase):
    def test_quit_message_counts_records_not_filtered_items(self):
        with patch.object(ocore, "instance_records", return_value=[{}, {}]):
            self.assertEqual(dashboard.quit_message(), " quit and stop 2 instance(s)?")

    def test_screen_command_prints_the_published_dashboard(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_state = ocore.STATE
            ocore.STATE = Path(tmp)
            try:
                (ocore.STATE / "dashboard-screen.txt").write_text("dashboard\n")
                output = io.StringIO()
                with redirect_stdout(output):
                    self.assertEqual(ocore._cmd_screen(None), 0)
                self.assertEqual(output.getvalue(), "dashboard\n")
            finally:
                ocore.STATE = old_state

    def test_minimized_state_round_trips_and_prunes_unknown_sessions(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(ocore, "STATE", Path(tmp)):
                dashboard.save_minimized({"session-1", "session-2"})
                self.assertEqual(dashboard.load_minimized({"session-2", "session-3"}),
                                 {"session-2"})

    def test_minimized_state_is_not_pruned_before_first_snapshot(self):
        data = dashboard.Data.__new__(dashboard.Data)
        data.stamp = 0
        minimized = {"session-1"}
        items = []
        session_ids = {item["session_id"] for item in items}
        if data.stamp:
            minimized &= session_ids
        self.assertEqual(minimized, {"session-1"})

    def test_completed_placeholder_has_bounded_lifetime(self):
        with patch.object(ocore, "jira_cache", return_value={}), \
             patch.object(ocore, "new_instance", return_value={"session_id": "session-1"}):
            data = dashboard.Data()
            data.create("do the work", "/tmp/project", None)
            data.wait_creations()
            self.assertIn("completed_at", data.pending[0])

    def test_new_instance_has_a_placeholder_until_creation_finishes(self):
        started = threading.Event()
        release = threading.Event()

        def create(*args, **kwargs):
            started.set()
            release.wait(2)
            return {"session_id": "session-1"}

        with patch.object(ocore, "jira_cache", return_value={}), \
             patch.object(ocore, "new_instance", side_effect=create):
            data = dashboard.Data()
            data.create("do the work", "/tmp/project", "feature")
            self.assertTrue(started.wait(1))
            items, _, _, _ = data.read()
            self.assertEqual(len(items), 1)
            self.assertTrue(items[0]["pending"])
            self.assertEqual(items[0]["state"], "working")
            release.set()
            data.wait_creations()
            self.assertEqual(data._creation_threads, [])
            items, _, _, _ = data.read()
            self.assertEqual(items[0]["real_session_id"], "session-1")
            self.assertEqual(data.take_completions()[0][1]["session_id"], "session-1")

    def test_completed_creation_thread_is_released_without_shutdown(self):
        with patch.object(ocore, "jira_cache", return_value={}), \
             patch.object(ocore, "new_instance", return_value={"session_id": "session-1"}):
            data = dashboard.Data()
            data.create("do the work", "/tmp/project", None)
            for _ in range(100):
                if not data._creation_threads:
                    break
                time.sleep(0.01)
            self.assertEqual(data._creation_threads, [])


class CoreTests(unittest.TestCase):
    def test_failed_prompt_removes_record_and_aborts_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_instances = ocore.INSTANCES
            ocore.INSTANCES = Path(tmp)
            try:
                with patch.object(ocore, "server_url", return_value="http://server"), \
                     patch.object(ocore, "http", return_value={"id": "session-1"}), \
                     patch.object(ocore, "send_prompt", side_effect=ocore.ApiError("failed")), \
                     patch.object(ocore, "abort_instance") as abort:
                    with self.assertRaises(ocore.ApiError):
                        ocore.new_instance("do the work")
                abort.assert_called_once_with("session-1")
                self.assertFalse((Path(tmp) / "session-1.json").exists())
            finally:
                ocore.INSTANCES = old_instances

    def test_permission_defaults_are_unattended(self):
        with patch.dict("os.environ", {}, clear=True):
            permissions = json.loads(ocore.permission_json())
        self.assertEqual(permissions["read"], "allow")
        self.assertEqual(permissions["bash"], "allow")
        self.assertEqual(permissions["edit"], "allow")

    def test_read_only_is_available_on_request(self):
        with patch.dict("os.environ", {"OPENDASH_AUTO": "0"}, clear=True):
            permissions = json.loads(ocore.permission_json())
        self.assertNotIn("bash", permissions)

    def test_invalid_permission_value_is_rejected(self):
        with patch.dict("os.environ", {"OPENDASH_PERMISSION": "allow"}, clear=True):
            with self.assertRaises(ocore.ApiError):
                ocore.permission_json()

    def test_stale_pid_is_not_considered_owned(self):
        result = type("Result", (), {"returncode": 0, "stdout": "python worker.py\n"})()
        with patch.object(ocore.subprocess, "run", return_value=result):
            self.assertFalse(ocore._server_process_owned({"pid": 123}))


if __name__ == "__main__":
    unittest.main()


class ServerUrlTests(unittest.TestCase):
    """A busy live server must not be replaced on one failed probe."""

    INFO = {"url": "http://127.0.0.1:49964", "port": 49964, "pid": 123}

    def test_second_probe_passing_keeps_the_recorded_server(self):
        probes = iter([False, True])            # busy once, then responsive
        with patch.object(ocore, "server_info", return_value=self.INFO), \
             patch.object(ocore, "_server_process_owned", return_value=True), \
             patch.object(ocore, "_server_alive", side_effect=lambda *a, **k: next(probes)), \
             patch.object(ocore, "_start_server") as start:
            self.assertEqual(ocore.server_url(), self.INFO["url"])
            start.assert_not_called()

    def test_owned_but_unresponsive_server_is_replaced_and_killed(self):
        with patch.object(ocore, "server_info", return_value=self.INFO), \
             patch.object(ocore, "_server_process_owned", return_value=True), \
             patch.object(ocore, "_server_alive", return_value=False), \
             patch.object(ocore, "_start_server", return_value="http://127.0.0.1:61054") as start:
            self.assertEqual(ocore.server_url(), "http://127.0.0.1:61054")
            start.assert_called_once_with(replace_pid=123)

    def test_owned_but_unresponsive_without_start_returns_none(self):
        with patch.object(ocore, "server_info", return_value=self.INFO), \
             patch.object(ocore, "_server_process_owned", return_value=True), \
             patch.object(ocore, "_server_alive", return_value=False), \
             patch.object(ocore, "_start_server") as start:
            self.assertIsNone(ocore.server_url(start=False))
            start.assert_not_called()

    def test_gone_pid_starts_fresh_without_a_replace(self):
        with patch.object(ocore, "server_info", return_value=self.INFO), \
             patch.object(ocore, "_server_process_owned", return_value=False), \
             patch.object(ocore, "_start_server", return_value="http://127.0.0.1:61054") as start:
            self.assertEqual(ocore.server_url(), "http://127.0.0.1:61054")
            start.assert_called_once_with()

    def test_replacement_kills_the_recorded_process_group(self):
        killed = []
        alive = iter([False, True])              # new server comes up
        tmp = ocore.Path(tempfile.mkdtemp())
        (tmp / "server.log").write_text("")
        with patch.object(ocore, "STATE", tmp), \
             patch.object(ocore, "SERVER_LOG", tmp / "server.log"), \
             patch.object(ocore, "_free_port", return_value=61054), \
             patch.object(ocore, "opencode_bin", return_value="opencode"), \
             patch.object(ocore, "_server_alive", side_effect=lambda *a, **k: next(alive)), \
             patch.object(ocore, "_server_process_owned", side_effect=lambda info: info["pid"] == 123), \
             patch.object(ocore.subprocess, "Popen") as popen, \
             patch.object(ocore.os, "killpg", side_effect=lambda pid, sig: killed.append((pid, sig))):
            popen.return_value.pid = 999
            popen.return_value.poll.return_value = None
            url = ocore._start_server(replace_pid=123)
            self.assertEqual(url, "http://127.0.0.1:61054")
            self.assertEqual(killed, [(123, 15)])  # the old group, SIGTERM


class AgentLabelsTests(unittest.TestCase):
    """cwd matching names the agent that started each subprocess."""

    RECORDS = [
        {"ticket": "PCYXC-2044", "directory": "/tmp/parrot",
         "worktree": "/tmp/codes-PCYXC-2044-x"},
        {"ticket": None, "directory": "/tmp/dotconfig", "worktree": None},
    ]

    def lsof(self, cwd_map):
        def fake_lsof(*argv, **kwargs):
            out = "".join(f"p{pid}\nn{cwd}\n" for pid, cwd in cwd_map.items())
            result = ocore.subprocess.CompletedProcess(argv, 0, stdout=out, stderr="")
            return result
        return fake_lsof

    def labels(self, cwd_map, pids):
        with patch.object(ocore, "instance_records", return_value=self.RECORDS), \
             patch.object(ocore.subprocess, "run", side_effect=self.lsof(cwd_map)):
            return ocore.agent_labels([{"pid": pid} for pid in pids])

    def test_subprocess_inside_worktree_is_attributed(self):
        got = self.labels({101: "/tmp/codes-PCYXC-2044-x/src"}, [101])
        self.assertEqual(got, {101: "PCYXC-2044"})

    def test_directory_without_ticket_uses_its_name(self):
        got = self.labels({102: "/tmp/dotconfig/sub"}, [102])
        self.assertEqual(got, {102: "dotconfig"})

    def test_unmatched_cwd_gets_no_label(self):
        got = self.labels({103: "/tmp/elsewhere"}, [103])
        self.assertEqual(got, {})

    def test_prefix_does_not_match_a_directory_mid_path(self):
        got = self.labels({104: "/tmp/parrot-something"}, [104])
        self.assertEqual(got, {})
