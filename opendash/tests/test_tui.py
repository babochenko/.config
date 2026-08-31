"""Level 5: the curses dashboard, driven in a real terminal.

The dashboard is run inside tmux with OPENDASH_NO_SERVER=1 and a stand-in
database, so the ui is exercised on its own: no opencode server, no agents, no
network. Assertions are made against what is actually on the screen.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
import unittest
from pathlib import Path

from support import ROOT, SCHEMA, have, now_ms, run

SOCKET = "opendash-tui-tests"


def tmux(*args, **kwargs):
    return run("tmux", "-L", SOCKET, *args, **kwargs)


@unittest.skipUnless(have("tmux"), "tmux is not installed")
class Dashboard(unittest.TestCase):
    """One dashboard, started once, driven by keystrokes."""

    @classmethod
    def setUpClass(cls):
        cls.dir = Path(run("mktemp", "-d").stdout.strip())
        cls.state = cls.dir / "state"
        (cls.state / "instances").mkdir(parents=True)
        cls.db = cls.dir / "opencode.db"
        con = sqlite3.connect(cls.db)
        con.executescript(SCHEMA)

        started = now_ms() - 60_000
        (cls.state / "server.json").write_text(json.dumps(
            {"url": "http://127.0.0.1:1", "port": 1, "pid": 1, "started": started}))

        # three instances: idle with a ticket, working, and one in a worktree
        for n, (sid, ticket, title, working, directory, agent) in enumerate([
            ("ses_aaaaaaaaaaaaaaaa1", "PROJ-1", "add subtract to calc", False, "/tmp/one", "build"),
            ("ses_bbbbbbbbbbbbbbbb2", None, "count the lines", True, "/tmp/two", "myagent"),
            ("ses_cccccccccccccccc3", "TIX-9", "fix the tests", False,
             "/tmp/codes-TIX-9-fix", "plan"),
        ]):
            (cls.state / "instances" / f"{sid}.json").write_text(json.dumps({
                "session_id": sid, "ticket": ticket, "task": "the original request",
                "directory": directory, "model": None, "agent": agent,
                "created": 1_000 + n, "worktree": directory if ticket == "TIX-9" else None,
                "branch": "TIX-9-fix" if ticket == "TIX-9" else None,
                "repo": "/tmp/codes" if ticket == "TIX-9" else None}))
            con.execute("insert into session (id, title, time_created, time_updated,"
                        " directory) values (?,?,?,?,?)",
                        (sid, title, started, started, directory))
            data = {"role": "assistant", "time": {"created": started + 1}}
            if not working:
                data["time"]["completed"] = started + 2
            con.execute("insert into message (id, session_id, time_created, data)"
                        " values (?,?,?,?)", (f"msg{n}", sid, started + 1, json.dumps(data)))
            text = "still going" if working else f"finished {n}"
            part = ({"type": "tool", "tool": "bash",
                     "state": {"status": "running", "input": {"command": "npm test"}}}
                    if working else {"type": "text", "text": text})
            con.execute("insert into part (id, message_id, session_id, time_created, data)"
                        " values (?,?,?,?,?)",
                        (f"prt{n}", f"msg{n}", sid, started + 1, json.dumps(part)))
        con.execute("insert into todo (session_id, content, status, position)"
                    " values (?,?,?,?)", ("ses_aaaaaaaaaaaaaaaa1", "done bit", "completed", 0))
        con.commit()
        con.close()

        tmux("kill-server")
        cls.env = (f"OPENDASH_STATE={cls.state} OPENCODE_DB={cls.db} "
                   f"OPENDASH_NO_SERVER=1 OPENDASH_TMUX_SOCKET=opendash-tui-inner "
                   f"OPENDASH_CONFIG={cls.dir}/none.json TERM=xterm-256color")
        cls.start("ui")

    @classmethod
    def start(cls, name: str):
        """A dashboard of its own, so a test that quits cannot blank the rest."""
        tmux("new-session", "-d", "-s", name, "-x", "200", "-y", "24", "-c", "/tmp",
             f"{cls.env} exec {ROOT}/opendash")
        for _ in range(40):
            if "opendash" in tmux("capture-pane", "-p", "-t", name).stdout:
                return
            time.sleep(0.25)
        raise AssertionError(f"dashboard {name} did not start")

    @classmethod
    def tearDownClass(cls):
        tmux("kill-server")
        run("tmux", "-L", "opendash-tui-inner", "kill-server")
        run("rm", "-rf", str(cls.dir))

    def setUp(self):
        """Start each test from a known screen: no prompt, no filter, top row."""
        for key in ("Escape", "Escape"):
            tmux("send-keys", "-t", "ui", key)
            time.sleep(0.2)
        tmux("send-keys", "-t", "ui", "g")
        time.sleep(0.5)

    # -- helpers -------------------------------------------------------------

    def screen(self) -> str:
        return tmux("capture-pane", "-p", "-t", "ui").stdout

    def press(self, *keys, settle: float = 0.6):
        for key in keys:
            tmux("send-keys", "-t", "ui", key)
            time.sleep(settle)

    def type(self, text: str, settle: float = 0.6):
        tmux("send-keys", "-t", "ui", "-l", text)
        time.sleep(settle)

    def selected(self) -> str:
        for line in self.screen().splitlines():
            if line.startswith("▌"):
                return line
        return ""

    # -- what is on the screen ----------------------------------------------

    def test_it_renders_every_instance(self):
        screen = self.screen()
        self.assertIn("3 instances", screen)
        for fragment in ("PROJ-1", "add subtract to calc", "count the lines",
                         "TIX-9", "fix the tests"):
            self.assertIn(fragment, screen)

    def test_the_row_shows_state_progress_and_directory(self):
        screen = self.screen()
        self.assertIn("idle", screen)
        self.assertIn("working", screen)
        self.assertIn("✓1/1", screen)              # the completed todo
        self.assertIn("codes-TIX-9-fix", screen)        # last directory component

    def test_the_row_shows_the_branch_name(self):
        screen = self.screen()
        self.assertIn("TIX-9-fix", screen)

    def test_a_working_instance_says_what_it_is_doing(self):
        self.assertIn("npm test", self.screen())

    def test_instances_are_listed_in_start_order(self):
        screen = self.screen()
        self.assertLess(screen.index("add subtract"), screen.index("count the lines"))
        self.assertLess(screen.index("count the lines"), screen.index("fix the tests"))

    def test_the_footer_advertises_the_keys(self):
        for key in ("j/k move", "J/K reorder", "t term", "n new", "d remove",
                    "r/R rename", "z minimize", "q leave", "Q quit"):
            self.assertIn(key, self.screen())

    def test_z_minimizes_and_restores_the_selected_instance(self):
        self.press("g", "z")
        screen = self.screen()
        self.assertIn("brand new name", screen)
        self.assertNotIn("finished 0", screen)
        self.press("z")
        self.assertIn("finished 0", self.screen())

    # -- driving it ----------------------------------------------------------

    def test_j_and_k_move_the_cursor(self):
        self.press("g")
        self.assertIn("add subtract", self.selected())
        self.press("j")
        self.assertIn("count the lines", self.selected())
        self.press("k")
        self.assertIn("add subtract", self.selected())
        self.press("G")
        self.assertIn("fix the tests", self.selected())
        self.press("g")

    def test_J_reorders_and_K_puts_it_back(self):
        self.press("g", "J")
        screen = self.screen()
        self.assertLess(screen.index("count the lines"), screen.index("add subtract"))
        self.assertIn("add subtract", self.selected())     # cursor follows the row
        time.sleep(2)                                      # survive a background poll
        screen = self.screen()
        self.assertLess(screen.index("count the lines"), screen.index("add subtract"))
        self.press("K")
        screen = self.screen()
        self.assertLess(screen.index("add subtract"), screen.index("count the lines"))

    def test_filtering_narrows_the_list_and_escape_clears_it(self):
        self.press("/")
        self.type("TIX")
        self.press("Enter")
        screen = self.screen()
        self.assertIn("1 instance", screen)
        self.assertNotIn("add subtract", screen)
        self.press("Escape")
        self.assertIn("3 instances", self.screen())

    def test_the_help_overlay_opens_and_closes(self):
        self.press("?")
        screen = self.screen()
        self.assertIn("keys", screen)
        self.assertIn("move the cursor", screen)
        self.assertIn("rename", screen)
        self.press("q")                                   # any key closes it
        self.assertNotIn("move the cursor", self.screen())

    def test_rename_prefills_with_r_and_is_empty_with_R(self):
        self.press("g", "r")
        self.assertIn("add subtract", self.screen().splitlines()[-1])
        self.press("Escape")
        self.press("R")
        self.assertRegex(self.screen().splitlines()[-1].strip(), r"^title:$")
        self.press("Enter")                               # empty input does nothing
        self.assertIn("add subtract", self.screen())

    def test_renaming_changes_the_row_and_keeps_the_ticket(self):
        self.press("g", "R")
        self.type("brand new name")
        self.press("Enter", settle=1.5)
        row = self.selected()
        self.assertIn("brand new name", row)
        self.assertIn("PROJ-1", row)

    def test_remove_asks_first_and_n_keeps_it(self):
        self.press("g", "d")
        self.assertIn("remove", self.screen().splitlines()[-1])
        self.press("n", settle=1.2)
        self.assertIn("3 instances", self.screen())

    def test_removing_a_worktree_instance_warns_about_the_worktree(self):
        self.press("G", "d")
        prompt = self.screen().splitlines()[-1]
        self.assertIn("worktree", prompt)
        self.assertIn("branch is kept", prompt)
        self.press("n", settle=1.2)
        self.press("g")

    def test_abort_asks_first(self):
        self.press("g", "a")
        self.assertIn("abort", self.screen().splitlines()[-1])
        self.press("n", settle=1.2)

    def test_new_asks_for_the_directory_then_a_worktree_branch(self):
        self.press("n")
        self.assertIn("dir", self.screen().splitlines()[-1])
        self.press("Enter")
        self.assertIn("tree", self.screen().splitlines()[-1])
        self.press("Escape", settle=1.2)
        self.assertIn("3 instances", self.screen())

    def test_the_server_is_reported_as_down_without_one(self):
        self.assertIn("server down", self.screen())

    def test_q_leaves_the_dashboard(self):
        self.start("ui-quit")                     # its own, so the suite survives
        tmux("send-keys", "-t", "ui-quit", "q")
        time.sleep(1.5)
        self.assertEqual(tmux("has-session", "-t", "=ui-quit").returncode, 1,
                         "the dashboard should have exited")


if __name__ == "__main__":
    unittest.main()
