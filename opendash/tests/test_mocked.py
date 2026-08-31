import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from support import ROOT  # noqa: F401  (puts opendash on sys.path)

import dashboard
import ocore


class DashboardTests(unittest.TestCase):
    def test_quit_message_counts_records_not_filtered_items(self):
        with patch.object(ocore, "instance_records", return_value=[{}, {}]):
            self.assertEqual(dashboard.quit_message(), " quit and stop 2 instance(s)?")

    def test_minimized_state_round_trips_and_prunes_unknown_sessions(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(ocore, "STATE", Path(tmp)):
                dashboard.save_minimized({"session-1", "session-2"})
                self.assertEqual(dashboard.load_minimized({"session-2", "session-3"}),
                                 {"session-2"})

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
            items, _, _, _ = data.read()
            self.assertEqual(items, [])
            self.assertEqual(data.take_completions()[0][1]["session_id"], "session-1")


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
