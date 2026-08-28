import json
import sys
import tempfile
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
