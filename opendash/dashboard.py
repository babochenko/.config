#!/usr/bin/env python3
"""
opendash -- curses dashboard for background opencode instances.

Two lines per instance: what it was asked to do, and what it has done so far.
Arrows or hjkl to move, enter or o to open the instance, option+q inside to come back.
"""
from __future__ import annotations

import contextlib
import curses
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
from pathlib import Path

import ocore
import metadata

REFRESH = 1.5          # seconds between db snapshots
METADATA_EVERY = 5.0   # wake the worker; remote cache TTL controls actual polls
TICK_MS = 120          # ui tick; also the spinner rate

SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
AGE_W = 5              # right-aligned age column
TERM_W = 10            # how much of a running terminal command to show

ICONS = {
    "working":   None,        # animated spinner
    "attention": "◆",
    "queued":    "◔",
    "idle":      "●",
    "error":     "✖",
    "unknown":   "○",
}

LABELS = {
    "working":   "working",
    "attention": "needs you",
    "queued":    "queued",
    "idle":      "idle",
    "error":     "error",
    "unknown":   "gone",
}

# color pair ids
C_WORK, C_OK, C_ERR, C_ATT, C_DIM, C_TICKET, C_ACCENT, C_SEL = range(1, 9)

STATE_COLOR = {
    "working": C_WORK, "attention": C_ATT, "queued": C_ACCENT,
    "idle": C_OK, "error": C_ERR, "unknown": C_DIM,
}

JIRA_COLOR = {"todo": C_DIM, "progress": C_WORK, "done": C_OK}


# ------------------------------------------------------------------ text utils

def _w(ch: str) -> int:
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def clip(text: str, width: int) -> str:
    """Truncate to a printed width, ellipsising when it does not fit."""
    if width <= 0:
        return ""
    text = text.replace("\t", " ")
    total = sum(_w(c) for c in text)
    if total <= width:
        return text
    out, used = [], 0
    for c in text:
        cw = _w(c)
        if used + cw > width - 1:
            break
        out.append(c)
        used += cw
    return "".join(out) + "…"


def printw(win, y: int, x: int, text: str, attr=0) -> int:
    """Write clipped to the window, returning the next free column."""
    maxy, maxx = win.getmaxyx()
    if y < 0 or y >= maxy or x >= maxx - 1:
        return x
    text = clip(text, maxx - 1 - x)
    if not text:
        return x
    try:
        win.addstr(y, x, text, attr)
    except curses.error:
        pass
    return x + sum(_w(c) for c in text)


# --------------------------------------------------------------- data plumbing

class Data:
    """Background poller so the UI never blocks on sqlite, http or jira."""

    def __init__(self):
        self.lock = threading.Lock()
        self.items: list[dict] = []
        self.jira: dict = ocore.jira_cache()
        self.pr: dict = metadata.pr_cache(ocore.STATE)
        self.server_up = False
        self.error: str | None = None
        self.stamp = 0.0
        self._stop = threading.Event()
        self._wake = threading.Event()
        self.pending: list[dict] = []
        self.completions: list[tuple[dict, dict | None, str | None]] = []
        self._creation_threads: list[threading.Thread] = []
        self._creation_number = 0
        self._order_override: list[str] = []

    def start(self):
        threading.Thread(target=self._loop, daemon=True).start()
        threading.Thread(target=self._jira_loop, daemon=True).start()

    def stop(self):
        self._stop.set()
        self._wake.set()

    def refresh_now(self):
        self._wake.set()

    def create(self, task: str, directory: str, worktree: str | None) -> None:
        """Create an instance off the UI thread while showing a local placeholder."""
        with self.lock:
            self._creation_number += 1
            number = self._creation_number
            now = ocore.now_ms()
            pending = {
                "session_id": f"pending-{number}",
                "task": task,
                "directory": directory,
                "worktree": None,
                "branch": worktree,
                "created": now,
                "last_activity": now,
                "state": "working",
                "activity": ("running", "creating worktree…" if worktree
                             else "starting instance…"),
                "pending": True,
                "git": {"branch": worktree} if worktree else {},
            }
            self.pending.append(pending)

        def run() -> None:
            record, error = None, None
            try:
                record = ocore.new_instance(task, directory=directory,
                                            worktree=worktree or None)
            except Exception as e:
                error = f"{type(e).__name__}: {e}"[:160]
            with self.lock:
                self.pending[:] = [item for item in self.pending
                                   if item["session_id"] != pending["session_id"]]
                self.completions.append((pending, record, error))
            self.refresh_now()

        thread = threading.Thread(target=run, daemon=True)
        with self.lock:
            self._creation_threads.append(thread)
        thread.start()

    def take_completions(self):
        with self.lock:
            completions, self.completions = self.completions, []
            return completions

    def wait_creations(self):
        with self.lock:
            threads = list(self._creation_threads)
        for thread in threads:
            thread.join()

    def _loop(self):
        while not self._stop.is_set():
            try:
                items = ocore.snapshot(ocore.instance_records())
                info = ocore.server_info()
                up = bool(info and ocore._server_alive(info["url"], timeout=1.5))
                terminals = ocore.terminal_activity(items)
                for it in items:
                    it["terminal"] = terminals.get(it["session_id"])
                    it["git"] = ocore.git_summary(it.get("directory") or "")
                    it["pr_info"] = [self.pr.get(metadata._candidate_key(p),
                                                  self.pr.get(str(p.get("number")), p))
                                      for p in it.get("prs", [])]
                blocked = ocore.pending_attention(items) if up else {}
                for it in items:
                    note = blocked.get(it["session_id"])
                    if note:
                        it["state"] = "attention"
                        it["attention"] = note
                with self.lock:
                    if self._order_override:
                        by_id = {item["session_id"]: item for item in items}
                        ordered = [by_id[sid] for sid in self._order_override if sid in by_id]
                        ordered.extend(item for item in items
                                       if item["session_id"] not in self._order_override)
                        items = ordered
                    self.items, self.server_up, self.error = items, up, None
                    self.stamp = time.time()
            except Exception as e:                      # keep the ui alive
                with self.lock:
                    self.error = f"{type(e).__name__}: {e}"[:120]
            self._wake.wait(REFRESH)
            self._wake.clear()

    def _jira_loop(self):
        while not self._stop.is_set():
            try:
                with self.lock:
                    tickets = sorted({i["ticket"] for i in self.items if i.get("ticket")})
                    prs = [p for i in self.items for p in i.get("prs", [])]
                if tickets or prs:
                    cache, pr_cache = metadata.refresh_remote(ocore.STATE, tickets, prs)
                    with self.lock:
                        self.jira = cache
                        self.pr = pr_cache
                        for item in self.items:
                            item["pr_info"] = [pr_cache.get(metadata._candidate_key(p),
                                                              pr_cache.get(str(p.get("number")), p))
                                                for p in item.get("prs", [])]
                            if not item.get("ticket") and not item.get("ticket_manual"):
                                for info in item["pr_info"]:
                                    if info.get("tickets"):
                                        item["ticket"] = info["tickets"][0]
                                        metadata.associate_ticket(ocore.STATE, item["session_id"], item["ticket"])
                                        break
            except Exception:
                pass
            self._stop.wait(METADATA_EVERY)

    def reorder(self, a_sid: str, b_sid: str) -> None:
        """Reflect a manual move at once, without waiting for the next poll."""
        with self.lock:
            pos = {it["session_id"]: n for n, it in enumerate(self.items)}
            if a_sid in pos and b_sid in pos:
                i, j = pos[a_sid], pos[b_sid]
                self.items[i], self.items[j] = self.items[j], self.items[i]
                self._order_override = [item["session_id"] for item in self.items]

    def read(self):
        with self.lock:
            return (list(self.items) + list(self.pending), dict(self.jira),
                    self.server_up, self.error)


# ------------------------------------------------------------------ ui widgets

@contextlib.contextmanager
def blocking(stdscr):
    """Read keys blocking, then restore the animation tick."""
    stdscr.timeout(-1)
    try:
        yield
    finally:
        stdscr.timeout(TICK_MS)


def ask(stdscr, label: str, default: str = "") -> str | None:
    """One-line editor on the last row. Returns None on escape."""
    maxy, maxx = stdscr.getmaxyx()
    buf = list(default)
    pos = len(buf)
    curses.curs_set(1)
    with blocking(stdscr):
      try:
          while True:
              row = maxy - 1
              stdscr.move(row, 0)
              stdscr.clrtoeol()
              printw(stdscr, row, 0, label, curses.color_pair(C_ACCENT) | curses.A_BOLD)
              off = len(label) + 1
              text = "".join(buf)
              visible = maxx - off - 2
              start = max(0, pos - visible + 1)
              printw(stdscr, row, off, text[start:start + visible])
              try:
                  stdscr.move(row, min(maxx - 1, off + pos - start))
              except curses.error:
                  pass
              stdscr.refresh()
              ch = stdscr.get_wch()
              if isinstance(ch, str):
                  if ch in ("\x1b",):
                      return None
                  if ch in ("\n", "\r"):
                      return "".join(buf).strip()
                  if ch in ("\x7f", "\b"):
                      if pos:
                          del buf[pos - 1]
                          pos -= 1
                  elif ch == "\x15":                      # ctrl+u
                      buf, pos = [], 0
                  elif ch == "\x17":                      # ctrl+w
                      while pos and buf[pos - 1] == " ":
                          del buf[pos - 1]; pos -= 1
                      while pos and buf[pos - 1] != " ":
                          del buf[pos - 1]; pos -= 1
                  elif ch == "\x01":                      # ctrl+a
                      pos = 0
                  elif ch == "\x05":                      # ctrl+e
                      pos = len(buf)
                  elif ch.isprintable():
                      buf.insert(pos, ch)
                      pos += 1
              else:
                  if ch == curses.KEY_LEFT:
                      pos = max(0, pos - 1)
                  elif ch == curses.KEY_RIGHT:
                      pos = min(len(buf), pos + 1)
                  elif ch == curses.KEY_HOME:
                      pos = 0
                  elif ch == curses.KEY_END:
                      pos = len(buf)
                  elif ch == curses.KEY_BACKSPACE:
                      if pos:
                          del buf[pos - 1]; pos -= 1
                  elif ch == curses.KEY_RESIZE:
                      maxy, maxx = stdscr.getmaxyx()
      finally:
          curses.curs_set(0)


def confirm(stdscr, message: str) -> bool:
    maxy, _ = stdscr.getmaxyx()
    stdscr.move(maxy - 1, 0)
    stdscr.clrtoeol()
    printw(stdscr, maxy - 1, 0, f"{message} [y/N] ",
           curses.color_pair(C_ERR) | curses.A_BOLD)
    stdscr.refresh()
    with blocking(stdscr):
        try:
            ch = stdscr.get_wch()
        except curses.error:
            return False
    return isinstance(ch, str) and ch.lower() == "y"


def quit_message() -> str:
    """Describe the global quit operation without depending on the filter."""
    records = ocore.instance_records()
    count = len(records)
    return f" quit and stop {count} instance(s)?"


def compose(stdscr, directory: str) -> str | None:
    """Write the task in nvim, so it can be as long as it needs to be.

    Returns None if the editor was abandoned (`:cq`) or nothing was written.
    """
    editor = (os.environ.get("OPENDASH_EDITOR") or shutil.which("nvim")
              or os.environ.get("EDITOR") or "vi")
    with tempfile.TemporaryDirectory(prefix="opendash-") as tmp:
        # the filename shows up in nvim's statusline, naming the target dir
        path = Path(tmp) / f"task-in-{Path(directory).name or 'task'}.md"
        path.write_text("")
        curses.def_prog_mode()
        curses.endwin()
        rc, err = 1, None
        try:
            rc = subprocess.run([*shlex.split(editor), str(path)],
                                cwd=directory).returncode
        except OSError as e:
            err = f"{editor}: {e}"
        finally:
            curses.reset_prog_mode()
            stdscr.clear()
            stdscr.refresh()
        if err:
            error_pause(stdscr, err)
            return None
        if rc != 0:
            return None
        return path.read_text().strip() or None


def error_pause(stdscr, message: str) -> None:
    """Show a failure and wait for a keypress before redrawing."""
    flash(stdscr, f" {message} — press any key"[:240], C_ERR)
    with blocking(stdscr):
        try:
            stdscr.get_wch()
        except curses.error:
            pass


def flash(stdscr, message: str, pair: int = C_ACCENT) -> None:
    maxy, _ = stdscr.getmaxyx()
    stdscr.move(maxy - 1, 0)
    stdscr.clrtoeol()
    printw(stdscr, maxy - 1, 0, message, curses.color_pair(pair))
    stdscr.refresh()


def load_minimized(session_ids: set[str]) -> set[str]:
    """Load minimized rows, discarding sessions that no longer exist."""
    stored = ocore._read_json(ocore.STATE / "dashboard.json", {})
    values = stored.get("minimized", []) if isinstance(stored, dict) else []
    return {sid for sid in values if isinstance(sid, str) and sid in session_ids}


def save_minimized(session_ids: set[str]) -> None:
    """Persist dashboard-only visual state atomically with other opendash state."""
    ocore._write_json(ocore.STATE / "dashboard.json",
                      {"minimized": sorted(session_ids)})


HELP = [
    ("j k · ↓ ↑", "move the cursor between instances"),
    ("z", "minimize or maximize the selected instance"),
    ("J K", "move the selected instance down / up the list"),
    ("g / G", "first / last"),
    ("enter, o or l", "open the instance (option+q comes back here)"),
    ("c", "code actions: h check, m merge master, p commit/push, s git status, r review, U update/restart"),
    ("t", "terminal in the instance's directory (option+q closes it,"),
    ("", "or just detaches if something is still running)"),
    ("n", "new instance — asks for the directory, then a worktree"),
    ("", "branch (blank to skip), then opens nvim for the task;"),
    ("", "save to start it, :cq or an empty buffer cancels"),
    ("f", "follow up: send another message without opening it"),
    ("a", "abort whatever the instance is doing right now (asks first)"),
    ("d", "stop and remove from the dashboard, asks first (the opencode"),
    ("", "session is kept, and a worktree is removed but its branch is not)"),
    ("/", "filter by ticket or title;  esc clears"),
    ("u", "unlink the selected ticket or PR association"),
    ("b", "open the selected ticket or PR in the browser"),
    ("r", "rename this instance, editing the current name"),
    ("R", "rename it starting from an empty prompt"),
    ("", "either way the ticket is kept, and empty input does nothing"),
    ("S", "restart the shared opencode server"),
    ("q or ctrl+c", "leave the dashboard — every instance keeps working"),
    ("Q", "quit: stop all instances and the shared server too"),
]

CODE_ACTIONS = [
    ("h", "run check in the instance's directory"),
    ("m", "merge master in the instance's directory"),
    ("p", "ask the agent to commit and push current changes"),
    ("s", "show the repository's gs output"),
    ("r", "review this branch; fix critical issues, summarize the rest"),
    ("U", "update the config checkout and relaunch the dashboard"),
    ("esc", "cancel"),
]


def help_overlay(stdscr) -> None:
    maxy, maxx = stdscr.getmaxyx()
    h, w = len(HELP) + 4, min(maxx - 4, 72)
    y0, x0 = max(0, (maxy - h) // 2), max(0, (maxx - w) // 2)
    win = curses.newwin(h, w, y0, x0)
    win.bkgd(" ", curses.color_pair(C_DIM))
    win.border()
    printw(win, 0, 2, " keys ", curses.color_pair(C_ACCENT) | curses.A_BOLD)
    for i, (key, desc) in enumerate(HELP):
        printw(win, i + 2, 3, f"{key:<16}", curses.color_pair(C_TICKET) | curses.A_BOLD)
        printw(win, i + 2, 20, desc)
    win.refresh()
    with blocking(stdscr):
        try:
            stdscr.get_wch()
        except curses.error:
            pass
    del win
    stdscr.touchwin()
    stdscr.refresh()


def code_actions_overlay(stdscr) -> str | None:
    """Show code actions and return the selected action, if any."""
    maxy, maxx = stdscr.getmaxyx()
    h, w = len(CODE_ACTIONS) + 4, min(maxx - 4, 72)
    y0, x0 = max(0, (maxy - h) // 2), max(0, (maxx - w) // 2)
    win = curses.newwin(h, w, y0, x0)
    win.bkgd(" ", curses.color_pair(C_DIM))
    win.border()
    printw(win, 0, 2, " code actions ", curses.color_pair(C_ACCENT) | curses.A_BOLD)
    choice = None
    for i, (key, desc) in enumerate(CODE_ACTIONS):
        printw(win, i + 2, 3, f"{key:<16}", curses.color_pair(C_TICKET) | curses.A_BOLD)
        printw(win, i + 2, 20, desc)
    win.refresh()
    with blocking(stdscr):
        try:
            ch = stdscr.get_wch()
            if isinstance(ch, str) and ch in ("h", "m", "p", "s", "r", "U"):
                choice = ch
        except curses.error:
            pass
    del win
    stdscr.touchwin()
    stdscr.refresh()
    return choice


_ANSI_SGR = re.compile(r"\x1b\[([0-9;]*)m")


def _ansi_segments(text: str) -> list[tuple[str, int]]:
    """Convert the small ANSI palette emitted by git-status.awk to curses."""
    colors = {"32": C_OK, "31": C_ERR, "38;5;244": C_DIM}
    segments = []
    pair = C_DIM
    pos = 0
    for match in _ANSI_SGR.finditer(text):
        if match.start() > pos:
            segments.append((text[pos:match.start()], pair))
        code = match.group(1)
        pair = colors.get(code, C_DIM) if code != "0" else C_DIM
        pos = match.end()
    if pos < len(text):
        segments.append((text[pos:], pair))
    return segments


def _print_link(win, y: int, x: int, label: str, url: str | None, attr=0) -> int:
    """Print an OSC 8 link without counting its control sequence as width."""
    text = _osc8(label, url)
    maxx = win.getmaxyx()[1]
    if x >= maxx - 1:
        return x
    try:
        win.addstr(y, x, text, attr)
    except curses.error:
        pass
    return x + sum(_w(c) for c in label)


def git_status_overlay(stdscr, directory: str) -> None:
    """Show the exact ``gs`` output for a directory in a scrollable modal."""
    output, _ = ocore.git_status_output(directory)
    lines = output.splitlines() or ["no output"]
    maxy, maxx = stdscr.getmaxyx()
    height = min(maxy - 4, max(7, len(lines) + 4))
    width = min(maxx - 4, max(40, max(sum(len(segment) for segment, _ in _ansi_segments(line))
                                      for line in lines) + 8))
    top = 0
    while True:
        win = curses.newwin(height, width, max(0, (maxy - height) // 2),
                            max(0, (maxx - width) // 2))
        win.bkgd(" ", curses.color_pair(C_DIM))
        win.border()
        printw(win, 0, 2, " git status ", curses.color_pair(C_ACCENT) | curses.A_BOLD)
        visible = max(1, height - 4)
        for row, line in enumerate(lines[top:top + visible], 2):
            x = 3
            for segment, pair in _ansi_segments(line):
                x = printw(win, row, x, segment, curses.color_pair(pair))
        if top > 0:
            printw(win, 1, width - 4, "↑", curses.color_pair(C_DIM))
        if top + visible < len(lines):
            printw(win, height - 2, width - 4, "↓", curses.color_pair(C_DIM))
        win.refresh()
        with blocking(stdscr):
            try:
                ch = stdscr.get_wch()
            except curses.error:
                ch = "\x1b"
        del win
        if ch in ("\x1b", "q", "?", "c"):
            break
        if ch in ("j", curses.KEY_DOWN):
            top = min(top + 1, max(0, len(lines) - visible))
        elif ch in ("k", curses.KEY_UP):
            top = max(0, top - 1)
        else:
            break
    stdscr.touchwin()
    stdscr.refresh()


# ------------------------------------------------------------------- rendering

def draw(stdscr, items, jira, server_up, error, sel, frame, filt, minimized) -> None:
    stdscr.erase()
    maxy, maxx = stdscr.getmaxyx()
    dim = curses.color_pair(C_DIM)

    working = sum(1 for i in items if i["state"] == "working")
    attention = sum(1 for i in items if i["state"] == "attention")
    parts = [f"{len(items)} instance" + ("s" if len(items) != 1 else "")]
    if working:
        parts.append(f"{working} working")
    if attention:
        parts.append(f"{attention} needs you")
    x = printw(stdscr, 0, 1, "opendash", curses.color_pair(C_ACCENT) | curses.A_BOLD)
    x = printw(stdscr, 0, x, "  " + " · ".join(parts), dim)
    right = ("server up" if server_up else "server down") + "  " + time.strftime("%H:%M:%S")
    printw(stdscr, 0, max(x + 2, maxx - len(right) - 2), right,
           curses.color_pair(C_OK if server_up else C_ERR))
    printw(stdscr, 1, 1, "─" * max(0, maxx - 2), dim)

    body_top, body_bot = 2, maxy - 2
    if error:
        printw(stdscr, body_top, 2, error, curses.color_pair(C_ERR))
        body_top += 1

    if not items:
        msg = ("no instances yet — press n to start one"
               if not filt else f"nothing matches “{filt}”")
        printw(stdscr, body_top + 1, 3, msg, dim)
    else:
        available = body_bot - body_top
        first = max(0, sel - 4)
        while first > 0:
            height = 2 if items[first - 1]["session_id"] in minimized else 4
            if height > available:
                break
            first -= 1
            available -= height
        y = body_top
        idx = first
        while idx < len(items):
            is_minimized = items[idx]["session_id"] in minimized
            height = 2 if is_minimized else 4
            if y + height > body_bot:
                break
            _draw_item(stdscr, y, items[idx], jira, idx == sel, frame, maxx,
                       is_minimized)
            y += height
            idx += 1
        if first > 0:
            printw(stdscr, body_top, maxx - 4, "↑", dim)
        if idx < len(items):
            printw(stdscr, body_bot - 1, maxx - 4, "↓", dim)

    printw(stdscr, maxy - 2, 1, "─" * max(0, maxx - 2), dim)
    footer = ("j/k move · J/K reorder · z minimize · ⏎ open · t term · n new · "
              "f follow · a abort · d remove · r/R rename · / filter · ? keys · "
              "q leave · Q quit")
    if filt:
        footer = f"filter: {filt}   (esc clears) · " + footer
    printw(stdscr, maxy - 1, 1, footer, dim)
    stdscr.noutrefresh()
    curses.doupdate()
    publish_screen(stdscr)


def publish_screen(stdscr) -> None:
    """Publish the current curses characters for diagnostics and automation."""
    maxy, maxx = stdscr.getmaxyx()
    try:
        lines = [stdscr.instr(row, 0, maxx).decode(errors="replace").rstrip()
                 for row in range(maxy)]
        path = ocore.STATE / "dashboard-screen.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text("\n".join(lines) + "\n")
        tmp.replace(path)
    except (OSError, curses.error):
        pass


def _location_label(item: dict, branch: str | None) -> str:
    directory = item.get("directory") or ""
    if not item.get("worktree"):
        name = Path(directory).name or directory
        return f"▣ {name}  ⎇ {branch}" if branch else f"▣ {name}"

    repo = item.get("repo")
    if repo:
        name = Path(repo).name
    else:
        worktree_name = Path(item["worktree"]).name
        suffix = f"-{branch}" if branch else ""
        name = (worktree_name[:-len(suffix)] if suffix and worktree_name.endswith(suffix)
                else worktree_name)
    return f"▣ {name}  ⤷ {branch}" if branch else f"▣ {name}"


def _short_dir(directory: str | None) -> str:
    """Shorten a path for callers that need more than the row's final name."""
    if not directory:
        return ""
    home = str(Path.home())
    return "~" + directory[len(home):] if directory.startswith(home) else directory


def _draw_item(stdscr, y, item, jira, selected, frame, maxx, minimized=False) -> None:
    state = item["state"]
    pair = curses.color_pair(C_DIM if minimized else STATE_COLOR.get(state, C_DIM))
    icon = ICONS.get(state) or SPINNER[frame % len(SPINNER)]

    marker_rows = (y, y + 1) if minimized else (y, y + 1, y + 2)
    for row in marker_rows:
        printw(stdscr, row, 0, "▌" if selected else " ",
               curses.color_pair(C_DIM if minimized else C_ACCENT) | curses.A_BOLD)

    title_attr = (curses.color_pair(C_DIM) if minimized
                  else (curses.A_BOLD if selected else 0))
    emphasis = 0 if minimized else curses.A_BOLD
    x = printw(stdscr, y, 2, icon, pair | emphasis)
    x += 1

    ticket = item.get("ticket")
    jinfo = jira.get(ticket) if ticket else None
    if jinfo:
        tile = {"todo": "○", "progress": "◐", "done": "●"}.get(jinfo.get("category"), "·")
        tile_attr = curses.color_pair(C_DIM if minimized else JIRA_COLOR.get(jinfo.get("category"), C_DIM))
        x = printw(stdscr, y, x, tile, tile_attr | emphasis)
        x = printw(stdscr, y, x, " ")
    if ticket:
        ticket_attr = curses.color_pair(C_DIM if minimized else C_TICKET) | emphasis
        x = printw(stdscr, y, x, ticket, ticket_attr)
        x = printw(stdscr, y, x, "  ")

    # right side of line 1, in fixed columns so it reads as a table:
    # jira status (or the run state when there is no ticket) then age
    age = ocore.fmt_age(item.get("last_activity"))
    status_text = (jinfo or {}).get("status")
    if status_text:
        status_pair = curses.color_pair(JIRA_COLOR.get(jinfo.get("category"), C_DIM))
    else:
        status_text = LABELS.get(state, state)
        status_pair = pair
    age_x = maxx - 2 - AGE_W
    status_x = age_x - 2 - len(status_text)
    if minimized:
        status_pair = curses.color_pair(C_DIM)
    printw(stdscr, y, status_x, status_text, status_pair | emphasis)
    printw(stdscr, y, age_x + max(0, AGE_W - len(age)), age, curses.color_pair(C_DIM))

    if minimized:
        branch = (item.get("git") or {}).get("branch") or item.get("branch")
        pr = (item.get("pr_info") or item.get("prs") or [None])[0]
        pr_suffix = ""
        if pr:
            pr_suffix = "  PR #" + str(pr.get("number"))
            if pr.get("status"):
                pr_suffix += f" {pr['status']}"
            if pr.get("approvals") is not None:
                pr_suffix += f" ✓{pr['approvals']}"
            if pr.get("needs_update"):
                pr_suffix += " !"
            if pr.get("unresolved_threads"):
                pr_suffix += f" threads:{pr['unresolved_threads']}"
            builds = pr.get("builds") or {}
            if any(k in builds for k in ("ok", "failed", "unavailable")):
                pr_suffix += f" ✓{builds.get('ok', 0)} ✖{builds.get('failed', 0)}"
        suffix = "  " + _location_label(item, branch) + pr_suffix
        printw(stdscr, y, x, clip(ocore._headline(item) + suffix, max(4, status_x - x - 2)),
               title_attr)
        return

    # a `t` terminal still running something gets its own spinner and command,
    # separate from the agent's state -- an idle agent can have a busy terminal
    headline_end = status_x
    running = item.get("terminal")
    if running is not None:
        if running:
            icon, label = SPINNER[frame % len(SPINNER)], clip(running, TERM_W)
            icon_pair, label_pair = C_TICKET, C_TICKET
        else:
            icon, label = ICONS["idle"], "idle"
            icon_pair, label_pair = C_OK, C_DIM
        term_text = f"{icon} ❯{label}"
        headline_end = status_x - 2 - len(term_text)
        printw(stdscr, y, headline_end, icon, curses.color_pair(icon_pair) | curses.A_BOLD)
        printw(stdscr, y, headline_end + 2, f"❯{label}", curses.color_pair(label_pair))

    gitinfo = item.get("git") or {}
    git_parts: list[tuple[str, int, str | None]] = []
    if gitinfo.get("ahead"):
        git_parts.append((f"↑{gitinfo['ahead']}", C_OK, None))
    if gitinfo.get("behind"):
        git_parts.append((f"↓{gitinfo['behind']}", C_ERR, None))
    if gitinfo.get("staged"):
        git_parts.append((f"+{gitinfo['staged']}", C_OK, None))
    if gitinfo.get("modified"):
        git_parts.append((f"~{gitinfo['modified']}", C_WORK, None))
    if gitinfo.get("untracked"):
        git_parts.append((f"?{gitinfo['untracked']}", C_TICKET, None))
    if gitinfo.get("adds") or gitinfo.get("dels"):
        git_parts.extend(((f"+{gitinfo.get('adds', 0)}", C_OK, None),
                          (f"-{gitinfo.get('dels', 0)}", C_ERR, None)))

    prs = item.get("pr_info") or item.get("prs") or []
    pr = prs[0] if prs else None
    if pr:
        number = str(pr.get("number") or "")
        git_parts.append((f"#{number}", C_DIM, None))
    comments = pr.get("unresolved_comments") or [] if pr else []

    if git_parts:
        total_width = sum(len(text) for text, _, _ in git_parts) + len(git_parts) - 1
        right_start = max(3, maxx - 2 - total_width)
        git_x = right_start
        for n, (text, color, url) in enumerate(git_parts):
            if n:
                git_x = printw(stdscr, y + 2, git_x, " ", curses.color_pair(C_DIM))
            git_x = _print_link(stdscr, y + 2, git_x, text, url, curses.color_pair(color))
    else:
        right_start = maxx - 2

    branch = gitinfo.get("branch") or item.get("branch")
    location = _location_label(item, branch)
    printw(stdscr, y + 2, 3, clip(location, max(4, right_start - 5)),
           curses.color_pair(C_DIM))

    if comments:
        thread_text = "threads: " + "; ".join(
            f"{comment.get('author', 'reviewer')}: {comment.get('text', '')}"
            for comment in comments[:3]
        )
        printw(stdscr, y + 1, 3, clip(thread_text, maxx - 6),
               curses.color_pair(C_DIM))

    printw(stdscr, y, x, clip(ocore._headline(item), max(4, headline_end - x - 2)),
           title_attr)

    # line 2: what has actually been done, then the counters
    meta = []
    prog = ocore._progress(item)
    if prog:
        meta.append(prog)
    if item.get("adds") or item.get("dels"):
        meta.append(f"+{item.get('adds', 0)}/-{item.get('dels', 0)}")
    if item.get("cost"):
        meta.append(f"${item['cost']:.2f}")
    meta_text = " · ".join(meta)

    note = item.get("attention") or ocore.worked_on(item)
    lead = "◆ " if state == "attention" else ("▸ " if state == "working" else "· ")
    avail = maxx - 6 - (len(meta_text) + 2 if meta_text else 0)
    x2 = printw(stdscr, y + 1, 3, lead, pair)
    printw(stdscr, y + 1, x2, clip(note, max(4, avail)),
           curses.color_pair(C_ATT) | curses.A_BOLD if state == "attention"
           else curses.color_pair(C_DIM))
    if meta_text:
        printw(stdscr, y + 1, maxx - 2 - len(meta_text), meta_text, curses.color_pair(C_DIM))

# ------------------------------------------------------------------- main loop

def run(stdscr, start_dir: str) -> None:
    curses.curs_set(0)
    curses.use_default_colors()
    for pair, fg in ((C_WORK, curses.COLOR_YELLOW), (C_OK, curses.COLOR_GREEN),
                     (C_ERR, curses.COLOR_RED), (C_ATT, curses.COLOR_MAGENTA),
                     (C_TICKET, curses.COLOR_CYAN), (C_ACCENT, curses.COLOR_BLUE),
                     (C_SEL, curses.COLOR_WHITE)):
        curses.init_pair(pair, fg, -1)
    curses.init_pair(C_DIM, 8, -1)
    stdscr.timeout(TICK_MS)

    data = Data()
    data.start()

    sel, filt, last_dir = 0, "", start_dir
    session_ids = {record["session_id"] for record in ocore.instance_records()}
    minimized = load_minimized(session_ids)
    while True:
        for pending, record, creation_error in data.take_completions():
            if creation_error:
                error_pause(stdscr, f"failed: {creation_error}")
            elif record:
                flash(stdscr, f" started {record.get('ticket') or record['session_id'][-8:]}",
                      C_OK)
        items, jira, server_up, error = data.read()
        if filt:
            low = filt.lower()
            items = [i for i in items
                     if low in (i.get("ticket") or "").lower()
                     or low in ocore._headline(i).lower()
                     or low in (i.get("directory") or "").lower()]
        sel = max(0, min(sel, len(items) - 1)) if items else 0
        frame = int(time.time() * (1000 / TICK_MS)) % len(SPINNER)
        draw(stdscr, items, jira, server_up, error, sel, frame, filt, minimized)

        try:
            ch = stdscr.get_wch()
        except curses.error:
            continue                                  # tick with no key
        cur = items[sel] if items else None
        if cur and cur.get("pending"):
            cur = None

        if isinstance(ch, int):
            if ch == curses.KEY_DOWN:
                ch = "j"
            elif ch == curses.KEY_UP:
                ch = "k"
            elif ch == curses.KEY_ENTER:
                ch = "\n"
            elif ch == curses.KEY_RIGHT:
                ch = "l"
            elif ch == curses.KEY_HOME:
                ch = "g"
            elif ch == curses.KEY_END:
                ch = "G"
            elif ch == curses.KEY_RESIZE:
                stdscr.erase()
                continue
            else:
                continue

        if ch in ("q", "\x03"):                     # leave; instances keep running
            data.stop()
            data.wait_creations()
            return
        elif ch == "Q":
            question = quit_message()
            if question.endswith("0 instance(s)?") or confirm(stdscr, question):
                flash(stdscr, " stopping instances…")
                try:
                    data.stop()
                    data.wait_creations()
                    ocore.quit_all()
                except Exception as e:
                    error_pause(stdscr, f"failed: {e}")
                return
        elif ch == "j":
            sel = min(sel + 1, max(0, len(items) - 1))
        elif ch == "k":
            sel = max(sel - 1, 0)
        elif ch in ("J", "K") and cur:
            delta = 1 if ch == "J" else -1
            target = sel + delta
            if filt:
                flash(stdscr, " clear the filter to reorder")
            elif 0 <= target < len(items):
                neighbour = items[target]["session_id"]
                if ocore.move_instance(cur["session_id"], delta):
                    data.reorder(cur["session_id"], neighbour)
                    sel = target
        elif ch == "g":
            sel = 0
        elif ch == "G":
            sel = max(0, len(items) - 1)
        elif ch == "z" and cur:
            sid = cur["session_id"]
            if sid in minimized:
                minimized.remove(sid)
            else:
                minimized.add(sid)
            save_minimized(minimized)
        elif ch in ("\n", "\r", "l", "o") and cur:
            _open(stdscr, data, cur)
        elif ch == "t" and cur:
            _open(stdscr, data, cur, terminal=True)
        elif ch == "c":
            action = code_actions_overlay(stdscr)
            if action == "U":
                data.stop()
                data.wait_creations()
                return True
            if action and cur:
                try:
                    if action == "p":
                        ocore.send_prompt(
                            cur["session_id"],
                            "Commit and push the current changes.",
                            cur.get("directory") or last_dir,
                        )
                        flash(stdscr, " asked agent to commit and push", C_OK)
                    elif action == "s":
                        git_status_overlay(stdscr, cur.get("directory") or last_dir)
                    elif action == "r":
                        directory = cur.get("directory") or last_dir
                        branch = ocore.review_branch(directory)
                        if not branch:
                            flash(stdscr, " review skipped on main/master")
                        else:
                            ocore.send_prompt(
                                cur["session_id"],
                                "Review all changes in this branch against main/master, "
                                "excluding merge commits. Include committed branch changes "
                                "and current staged/unstaged changes. Look specifically for "
                                "critical bugs and serious inefficiencies, and fix those "
                                "directly. For everything else, provide a concise roundup "
                                "with file references and recommended follow-ups. Do not "
                                "rewrite unrelated code.",
                                directory,
                            )
                            flash(stdscr, f" asked agent to review {branch}", C_OK)
                    else:
                        command = "check" if action == "h" else "gitmm"
                        ocore.run_terminal_command(cur, command)
                        flash(stdscr, f" started {command}", C_OK)
                except Exception as e:
                    error_pause(stdscr, f"failed: {e}")
                data.refresh_now()
        elif ch == "n":
            where = ask(stdscr, " dir :", last_dir)
            if where is not None:
                where = os.path.expanduser(where.strip() or last_dir)
                if not Path(where).is_dir():
                    error_pause(stdscr, f"no such directory: {where}")
                else:
                    last_dir = where
                    tree = ask(stdscr, " tree :", "")   # branch name, blank to skip
                    if tree is not None:
                        tree = tree.strip()
                        task = compose(stdscr, where)
                        if not task:
                            flash(stdscr, " cancelled — nothing written")
                        else:
                            data.create(task, where, tree)
                            flash(stdscr, " creating worktree…" if tree
                                  else " starting instance…")
                        data.refresh_now()
        elif ch == "f" and cur:
            msg = ask(stdscr, " follow up:")
            if msg:
                try:
                    # no model/agent: keep the session on whatever it is using
                    ocore.send_prompt(cur["session_id"], msg,
                                      cur.get("directory") or last_dir)
                    flash(stdscr, " sent", C_OK)
                except Exception as e:
                    error_pause(stdscr, f"failed: {e}")
                data.refresh_now()
        elif ch == "a" and cur:
            label = cur.get("ticket") or ocore._headline(cur)[:40]
            if confirm(stdscr, f" abort what “{label}” is doing?"):
                ocore.abort_instance(cur["session_id"])
                flash(stdscr, " aborted")
                data.refresh_now()
        elif ch == "u" and cur:
            association = cur.get("ticket")
            if not association and cur.get("prs"):
                association = f"#{cur['prs'][0].get('number')}"
            if association and confirm(stdscr, f" unlink {association} from this instance?"):
                if ocore.unlink_association(cur["session_id"], association):
                    flash(stdscr, f" unlinked {association}", C_OK)
                    data.refresh_now()
        elif ch == "b" and cur:
            try:
                _open_links(cur)
            except OSError as e:
                error_pause(stdscr, f"failed to open link: {e}")
        elif ch == "d" and cur:
            label = cur.get("ticket") or ocore._headline(cur)[:40]
            tree = cur.get("worktree")
            question = f" remove “{label}” from the dashboard?"
            if tree:
                question = (f" remove “{label}” and its worktree "
                            f"{Path(tree).name}? the branch is kept:")
            if confirm(stdscr, question):
                force = False
                if tree and ocore.worktree_dirty(cur):
                    force = confirm(stdscr, " worktree has uncommitted changes — "
                                            "discard them?")
                if tree and ocore.worktree_dirty(cur) and not force:
                    flash(stdscr, " kept — commit or stash first")
                else:
                    try:
                        ocore.remove_instance(cur["session_id"], force=force)
                    except Exception as e:
                        error_pause(stdscr, f"{e}")
                    data.refresh_now()
        elif ch in ("r", "R") and cur:
            name = ask(stdscr, " title:", ocore._headline(cur) if ch == "r" else "")
            if name:
                try:
                    ocore.rename_instance(cur["session_id"], name)
                    flash(stdscr, " renamed", C_OK)
                except Exception as e:
                    error_pause(stdscr, f"failed: {e}")
                data.refresh_now()
        elif ch == "S":
            if confirm(stdscr, " restart the shared opencode server?"):
                flash(stdscr, " restarting server…")
                ocore.stop_server()
                try:
                    ocore.server_url()
                    flash(stdscr, " server restarted", C_OK)
                except Exception as e:
                    error_pause(stdscr, f"failed: {e}")
                data.refresh_now()
        elif ch == "/":
            got = ask(stdscr, " filter:", filt)
            filt = got or ""
        elif ch == "\x1b":
            filt = ""
        elif ch == "?":
            help_overlay(stdscr)


def _open(stdscr, data, item, terminal: bool = False) -> None:
    curses.def_prog_mode()
    curses.endwin()
    err = None
    try:
        (ocore.attach_terminal if terminal else ocore.attach)(item)
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
    finally:
        curses.reset_prog_mode()
        stdscr.clear()
        stdscr.refresh()
        # tmux can deliver scroll escape bytes while curses is being restored;
        # drain typeahead after the terminal is active, not just before it.
        for _ in range(3):
            curses.flushinp()
            time.sleep(0.03)
    if err:
        error_pause(stdscr, err)
    data.refresh_now()


def _osc8(label: str, url: str | None) -> str:
    """Emit OSC 8, using tmux passthrough when the dashboard runs inside tmux."""
    if not url:
        return label
    link = f"\033]8;;{url}\033\\{label}\033]8;;\033\\"
    if os.environ.get("TMUX"):
        return f"\033Ptmux;\033{link}\033\\"
    return link


def _open_links(item: dict) -> None:
    urls = []
    if item.get("ticket"):
        url = ocore.ticket_url(item["ticket"])
        if url: urls.append(url)
    for pr in item.get("pr_info", [])[:1]:
        if pr.get("url"): urls.append(pr["url"])
    if urls:
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        for url in urls:
            subprocess.Popen([opener, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main() -> int:
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print("opendash: the dashboard needs a terminal "
              "(try `opendash list` when piping output)", file=sys.stderr)
        return 2
    if not os.environ.get("TERM"):
        os.environ["TERM"] = "xterm-256color"
    # ncurses waits a full second on a bare escape to see whether a sequence is
    # coming, which makes esc-to-clear-the-filter feel broken
    os.environ.setdefault("ESCDELAY", "25")
    start_dir = os.getcwd()
    # A server that will not start is not a reason to refuse to open: the header
    # reports it and S retries. OPENDASH_NO_SERVER skips the attempt entirely,
    # which is what the tests use to drive the ui on its own.
    if os.environ.get("OPENDASH_NO_SERVER") != "1":
        try:
            ocore.server_url()
        except ocore.ApiError as e:
            print(f"opendash: opencode server did not start: {e}", file=sys.stderr)
    restart = curses.wrapper(run, start_dir)
    if restart:
        try:
            result = subprocess.run(
                ["zsh", "-lic", "p config && gitsm"],
                capture_output=True, text=True, timeout=120,
            )
        except (OSError, subprocess.SubprocessError) as e:
            print(f"opendash: update failed: {e}", file=sys.stderr)
            return 1
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            print(f"opendash: update failed: {detail}", file=sys.stderr)
            return 1
        os.execv(sys.executable, [sys.executable, __file__])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
