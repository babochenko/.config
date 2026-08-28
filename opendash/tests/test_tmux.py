"""Level 4: the tmux layer -- real panes on a throwaway socket.

The interesting part is the option+q decision, which has been wrong twice:
first for `./gradlew` (tmux reports the pane as "bash") and then for shell
functions like `check` (it stays "zsh" for the whole run). Both are pinned here.
"""
from __future__ import annotations

import time
import unittest
from pathlib import Path

from support import ROOT, SandboxCase, have, run

SOCKET = "opendash-tests"
IDLE_CHECK = ROOT / "idle-check.sh"


def tmux(*args, **kwargs):
    return run("tmux", "-L", SOCKET, *args, **kwargs)


def settle(seconds: float = 1.5):
    time.sleep(seconds)


@unittest.skipUnless(have("tmux"), "tmux is not installed")
class IdleCheck(unittest.TestCase):
    """exit 0 means "closable": a t terminal sitting at an idle prompt."""

    @classmethod
    def setUpClass(cls):
        tmux("kill-server")
        cls.work = Path(run("mktemp", "-d").stdout.strip())
        # a shell script, so the pane's current command is an interpreter
        (cls.work / "gradlew").write_text("#!/bin/sh\nsleep 120\n")
        (cls.work / "gradlew").chmod(0o755)
        # ...and a shell function, so it stays the shell itself
        (cls.work / "fn.zsh").write_text(
            "function check() { local out; out=$(./gradlew checkstyleMain 2>&1); }\n")

    @classmethod
    def tearDownClass(cls):
        tmux("kill-server")
        run("rm", "-rf", str(cls.work))

    def pane(self, name: str, *, command: str | None = None, source_fn: bool = False):
        tmux("kill-session", "-t", f"={name}")
        tmux("new-session", "-d", "-s", name, "-x", "80", "-y", "20", "-c", str(self.work))
        self.wait_until_settled(name)
        if source_fn:
            tmux("send-keys", "-t", name, f"source {self.work}/fn.zsh", "Enter")
            settle(1.0)
        if command:
            tmux("send-keys", "-t", name, command, "Enter")
            settle(2.5)
        self.addCleanup(lambda: tmux("kill-session", "-t", f"={name}"))
        tty = tmux("display", "-p", "-t", name, "#{pane_tty}").stdout.strip()
        pid = tmux("display", "-p", "-t", name, "#{pane_pid}").stdout.strip()
        return name, tty, pid

    @staticmethod
    def wait_until_settled(name: str, timeout: float = 5.0):
        """tmux reuses tty numbers, so a new pane can briefly share its tty with
        the tail end of the previous one. Wait for only the shell to remain."""
        tty = tmux("display", "-p", "-t", name, "#{pane_tty}").stdout.strip()
        deadline = time.time() + timeout
        while time.time() < deadline:
            rows = run("ps", "-t", tty.removeprefix("/dev/"), "-o", "pid=").stdout.split()
            if len(rows) == 1:
                return
            time.sleep(0.2)

    def closable(self, name, tty, pid) -> bool:
        return run(str(IDLE_CHECK), name, tty, pid).returncode == 0

    def test_an_idle_terminal_is_closed(self):
        self.assertTrue(self.closable(*self.pane("sh-idle0001")))

    def test_a_running_binary_only_detaches(self):
        self.assertFalse(self.closable(*self.pane("sh-busy0001", command="sleep 120")))

    def test_a_running_shell_script_only_detaches(self):
        # tmux reports this pane as "bash"; a name test would close it
        name, tty, pid = self.pane("sh-busy0002", command="./gradlew test")
        self.assertEqual(tmux("display", "-p", "-t", name,
                              "#{pane_current_command}").stdout.strip(),
                         "bash", "precondition: the pane looks like a shell")
        self.assertFalse(self.closable(name, tty, pid))

    def test_a_running_shell_function_only_detaches(self):
        # `check` runs inside the pane's own zsh, so the name never changes
        name, tty, pid = self.pane("sh-busy0003", command="check", source_fn=True)
        self.assertEqual(tmux("display", "-p", "-t", name,
                              "#{pane_current_command}").stdout.strip(),
                         "zsh", "precondition: the pane still looks idle by name")
        self.assertFalse(self.closable(name, tty, pid))

    def test_an_opencode_view_always_detaches_even_when_idle(self):
        self.assertFalse(self.closable(*self.pane("oc-abcd1234")))

    def test_anything_unreadable_is_treated_as_busy(self):
        self.assertFalse(self.closable("sh-x", "", ""))
        self.assertFalse(self.closable("sh-x", "/dev/ttys999999", "1"))


@unittest.skipUnless(have("tmux"), "tmux is not installed")
class TerminalActivity(SandboxCase):
    """What the row shows for an instance's `t` terminal."""

    def setUp(self):
        super().setUp()
        self.socket = self.box.env["OPENDASH_TMUX_SOCKET"]
        self.addCleanup(lambda: run("tmux", "-L", self.socket, "kill-server"))

    def start(self, name, command=None):
        run("tmux", "-L", self.socket, "new-session", "-d", "-s", name,
            "-x", "80", "-y", "20", "-c", "/tmp")
        if command:
            run("tmux", "-L", self.socket, "send-keys", "-t", name, command, "Enter")
            settle(2.0)

    def test_no_terminal_is_absent_from_the_report(self):
        items = [{"session_id": "ses_xxxxxxxxNOVIEW01"}]
        self.assertEqual(self.ocore.terminal_activity(items), {})

    def test_an_idle_terminal_reports_an_empty_command(self):
        self.start("sh-IDLE0001")
        items = [{"session_id": "ses_xxxxxxxxIDLE0001"}]
        self.assertEqual(self.ocore.terminal_activity(items), {"ses_xxxxxxxxIDLE0001": ""})

    def test_a_busy_terminal_reports_the_command_as_typed(self):
        self.start("sh-BUSY0001", command="sleep 120 ")
        items = [{"session_id": "ses_xxxxxxxxBUSY0001"}]
        report = self.ocore.terminal_activity(items)
        self.assertIn("sleep 120", report.get("ses_xxxxxxxxBUSY0001", ""))

    def test_instances_without_a_view_are_not_invented(self):
        self.start("sh-IDLE0002")
        items = [{"session_id": "ses_xxxxxxxxIDLE0002"},
                 {"session_id": "ses_xxxxxxxxMISSING1"}]
        self.assertEqual(set(self.ocore.terminal_activity(items)),
                         {"ses_xxxxxxxxIDLE0002"})


if __name__ == "__main__":
    unittest.main()
