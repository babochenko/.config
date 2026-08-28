"""Shared scaffolding: a throwaway state dir and a stand-in opencode database.

Every level of the suite builds its own world under a temp dir, so nothing here
touches the real ~/.local/state/opendash or opencode.db.
"""
from __future__ import annotations

import contextlib
import importlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# The opencode tables opendash reads, with only the columns it looks at.
SCHEMA = """
create table session (
    id text primary key, title text, cost real default 0,
    tokens_input integer default 0, tokens_output integer default 0,
    summary_additions integer default 0, summary_deletions integer default 0,
    summary_files integer default 0, time_created integer, time_updated integer,
    model text, agent text, directory text
);
create table message (
    id text primary key, session_id text, time_created integer, data text
);
create table part (
    id text primary key, message_id text, session_id text,
    time_created integer, data text
);
create table todo (
    session_id text, content text, status text, position integer
);
"""


def now_ms() -> int:
    return int(time.time() * 1000)


class Sandbox:
    """A temp state dir plus a stand-in opencode db, wired through the env."""

    def __init__(self, server_started: int | None = None):
        self._tick = 0
        self.dir = Path(tempfile.mkdtemp(prefix="opendash-test-"))
        self.state = self.dir / "state"
        self.db = self.dir / "opencode.db"
        (self.state / "instances").mkdir(parents=True)
        with contextlib.closing(sqlite3.connect(self.db)) as con:
            con.executescript(SCHEMA)
        self.env = {
            "OPENDASH_STATE": str(self.state),
            "OPENCODE_DB": str(self.db),
            "OPENDASH_TMUX_SOCKET": f"odtest-{os.getpid()}",
            "OPENDASH_CONFIG": str(self.dir / "config.json"),   # deliberately absent
        }
        if server_started is not None:
            (self.state / "server.json").write_text(json.dumps(
                {"url": "http://127.0.0.1:1", "port": 1, "pid": 1,
                 "started": server_started}))

    # -- env -----------------------------------------------------------------

    def apply(self):
        """Point ocore at this sandbox. Returns the freshly reloaded module."""
        self._saved = {k: os.environ.get(k) for k in self.env}
        os.environ.update(self.env)
        import ocore
        return importlib.reload(ocore)

    def restore(self):
        for key, value in getattr(self, "_saved", {}).items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def cleanup(self):
        self.restore()
        shutil.rmtree(self.dir, ignore_errors=True)

    # -- fixtures ------------------------------------------------------------

    def record(self, session_id="ses_test0001", **extra) -> dict:
        rec = {"session_id": session_id, "ticket": None, "task": "do the thing",
               "directory": "/tmp", "model": None, "agent": None,
               "created": now_ms(), "worktree": None, "branch": None, "repo": None}
        rec.update(extra)
        (self.state / "instances" / f"{session_id}.json").write_text(json.dumps(rec))
        return rec

    def session(self, session_id="ses_test0001", title="New session - 2026-01-01T00:00:00.000Z",
                **cols):
        with contextlib.closing(sqlite3.connect(self.db)) as con, con:
            columns = {"id": session_id, "title": title, "time_created": now_ms(),
                       "time_updated": now_ms(), "directory": "/tmp", **cols}
            names = ", ".join(columns)
            marks = ", ".join("?" * len(columns))
            con.execute(f"insert into session ({names}) values ({marks})",
                        list(columns.values()))

    def next_ms(self) -> int:
        """Strictly increasing, so "the last message" is never ambiguous."""
        self._tick += 1
        return now_ms() + self._tick

    def message(self, session_id="ses_test0001", role="assistant", completed=True,
                error=None, when=None, message_id=None):
        when = when if when is not None else self.next_ms()
        data = {"role": role, "time": {"created": when}}
        if completed:
            data["time"]["completed"] = when
        if error:
            data["error"] = error
        mid = message_id or f"msg_{role}_{when}_{os.urandom(3).hex()}"
        with contextlib.closing(sqlite3.connect(self.db)) as con, con:
            con.execute("insert into message (id, session_id, time_created, data)"
                        " values (?,?,?,?)", (mid, session_id, when, json.dumps(data)))
        return mid

    def part(self, message_id, session_id="ses_test0001", when=None, **data):
        when = when or now_ms()
        with contextlib.closing(sqlite3.connect(self.db)) as con, con:
            con.execute("insert into part (id, message_id, session_id, time_created, data)"
                        " values (?,?,?,?,?)",
                        (f"prt_{os.urandom(4).hex()}", message_id, session_id, when,
                         json.dumps(data)))

    def todo(self, content, status, position, session_id="ses_test0001"):
        with contextlib.closing(sqlite3.connect(self.db)) as con, con:
            con.execute("insert into todo (session_id, content, status, position)"
                        " values (?,?,?,?)", (session_id, content, status, position))


class SandboxCase(unittest.TestCase):
    """Base case that gives each test a clean sandbox and a reloaded ocore."""

    server_started: int | None = None

    def setUp(self):
        self.box = Sandbox(server_started=self.server_started)
        self.ocore = self.box.apply()
        self.addCleanup(self.box.cleanup)


def have(tool: str) -> bool:
    return shutil.which(tool) is not None


def run(*args, **kwargs) -> subprocess.CompletedProcess:
    kwargs.setdefault("capture_output", True)
    kwargs.setdefault("text", True)
    kwargs.setdefault("timeout", 60)
    return subprocess.run(list(args), **kwargs)
