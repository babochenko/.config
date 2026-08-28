#!/usr/bin/env python3
"""
opendash -- curses dashboard for background opencode instances.

Two lines per instance: what it was asked to do, and what it has done so far.
Arrows or hjkl to move, enter to open the instance, option+q inside to come back.
"""
from __future__ import annotations

import contextlib
import curses
import os
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

REFRESH = 1.5          # seconds between db snapshots
JIRA_EVERY = 60.0      # seconds between jira polls (cache has its own TTL)
TICK_MS = 120          # ui tick; also the spinner rate

SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
AGE_W = 5              # right-aligned age column

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
        self.server_up = False
        self.error: str | None = None
        self.stamp = 0.0
        self._stop = threading.Event()
        self._wake = threading.Event()

    def start(self):
        threading.Thread(target=self._loop, daemon=True).start()
        threading.Thread(target=self._jira_loop, daemon=True).start()

    def stop(self):
        self._stop.set()
        self._wake.set()

    def refresh_now(self):
        self._wake.set()

    def _loop(self):
        while not self._stop.is_set():
            try:
                items = ocore.snapshot(ocore.instance_records())
                info = ocore.server_info()
                up = bool(info and ocore._server_alive(info["url"], timeout=1.5))
                blocked = ocore.pending_attention(items) if up else {}
                for it in items:
                    note = blocked.get(it["session_id"])
                    if note:
                        it["state"] = "attention"
                        it["attention"] = note
                with self.lock:
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
                if tickets:
                    cache = ocore.jira_refresh(tickets)
                    with self.lock:
                        self.jira = cache
            except Exception:
                pass
            self._stop.wait(JIRA_EVERY)

    def read(self):
        with self.lock:
            return list(self.items), dict(self.jira), self.server_up, self.error


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


HELP = [
    ("j / k / ↓ / ↑", "move between instances"),
    ("g / G", "first / last"),
    ("enter or l", "open the instance (option+q comes back here)"),
    ("t", "terminal in the instance's directory (option+q closes it,"),
    ("", "or just detaches if something is still running)"),
    ("n", "new instance — asks for the directory, then opens nvim"),
    ("", "for the task; save to start it, :cq or empty to cancel"),
    ("f", "follow up: send another message without opening it"),
    ("a", "abort whatever the instance is doing right now (asks first)"),
    ("d", "stop and remove from the dashboard, asks first (session is kept)"),
    ("/", "filter by ticket or title;  esc clears"),
    ("r", "rename this instance — the ticket is kept"),
    ("R", "refresh now (it already polls every 1.5s)"),
    ("S", "restart the shared opencode server"),
    ("q or ctrl+c", "leave the dashboard — every instance keeps working"),
    ("Q", "quit: stop all instances and the shared server too"),
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


# ------------------------------------------------------------------- rendering

def draw(stdscr, items, jira, server_up, error, sel, frame, filt) -> None:
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
        rows_per = 4
        capacity = max(1, (body_bot - body_top) // rows_per)
        first = max(0, min(sel - capacity // 2, len(items) - capacity))
        for idx in range(first, min(len(items), first + capacity)):
            _draw_item(stdscr, body_top + (idx - first) * rows_per,
                       items[idx], jira, idx == sel, frame, maxx)
        if first > 0:
            printw(stdscr, body_top, maxx - 4, "↑", dim)
        if first + capacity < len(items):
            printw(stdscr, body_bot - 1, maxx - 4, "↓", dim)

    printw(stdscr, maxy - 2, 1, "─" * max(0, maxx - 2), dim)
    footer = ("j/k move · enter open · t term · n new · f follow up · a abort · "
              "d remove · r rename · / filter · ? keys · q leave · Q quit all")
    if filt:
        footer = f"filter: {filt}   (esc clears) · " + footer
    printw(stdscr, maxy - 1, 1, footer, dim)
    stdscr.noutrefresh()
    curses.doupdate()


def _short_dir(directory: str | None) -> str:
    if not directory:
        return ""
    home = str(Path.home())
    return "~" + directory[len(home):] if directory.startswith(home) else directory


def _draw_item(stdscr, y, item, jira, selected, frame, maxx) -> None:
    state = item["state"]
    pair = curses.color_pair(STATE_COLOR.get(state, C_DIM))
    icon = ICONS.get(state) or SPINNER[frame % len(SPINNER)]

    for row in (y, y + 1, y + 2):
        printw(stdscr, row, 0, "▌" if selected else " ",
               curses.color_pair(C_ACCENT) | curses.A_BOLD)

    title_attr = curses.A_BOLD if selected else 0
    x = printw(stdscr, y, 2, icon, pair | curses.A_BOLD)
    x += 1

    ticket = item.get("ticket")
    if ticket:
        x = printw(stdscr, y, x, ticket, curses.color_pair(C_TICKET) | curses.A_BOLD)
        x = printw(stdscr, y, x, "  ")

    # right side of line 1, in fixed columns so it reads as a table:
    # jira status (or the run state when there is no ticket) then age
    age = ocore.fmt_age(item.get("last_activity"))
    jinfo = jira.get(ticket) if ticket else None
    status_text = (jinfo or {}).get("status")
    if status_text:
        status_pair = curses.color_pair(JIRA_COLOR.get(jinfo.get("category"), C_DIM))
    else:
        status_text = LABELS.get(state, state)
        status_pair = pair
    age_x = maxx - 2 - AGE_W
    status_x = age_x - 2 - len(status_text)
    printw(stdscr, y, status_x, status_text, status_pair | curses.A_BOLD)
    printw(stdscr, y, age_x + max(0, AGE_W - len(age)), age, curses.color_pair(C_DIM))
    printw(stdscr, y, x, clip(ocore._headline(item), max(4, status_x - x - 2)), title_attr)

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

    # line 3: where the agent is working
    printw(stdscr, y + 2, 3, _short_dir(item.get("directory")), curses.color_pair(C_DIM))


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
    while True:
        items, jira, server_up, error = data.read()
        if filt:
            low = filt.lower()
            items = [i for i in items
                     if low in (i.get("ticket") or "").lower()
                     or low in ocore._headline(i).lower()
                     or low in (i.get("directory") or "").lower()]
        sel = max(0, min(sel, len(items) - 1)) if items else 0
        frame = int(time.time() * (1000 / TICK_MS)) % len(SPINNER)
        draw(stdscr, items, jira, server_up, error, sel, frame, filt)

        try:
            ch = stdscr.get_wch()
        except curses.error:
            continue                                  # tick with no key
        cur = items[sel] if items else None

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
            return
        elif ch == "Q":
            question = quit_message()
            if question.endswith("0 instance(s)?") or confirm(stdscr, question):
                flash(stdscr, " stopping instances…")
                try:
                    ocore.quit_all()
                except Exception as e:
                    error_pause(stdscr, f"failed: {e}")
                data.stop()
                return
        elif ch == "j":
            sel = min(sel + 1, max(0, len(items) - 1))
        elif ch == "k":
            sel = max(sel - 1, 0)
        elif ch == "g":
            sel = 0
        elif ch == "G":
            sel = max(0, len(items) - 1)
        elif ch in ("\n", "\r", "l") and cur:
            _open(stdscr, data, cur)
        elif ch == "t" and cur:
            _open(stdscr, data, cur, terminal=True)
        elif ch == "n":
            where = ask(stdscr, " dir :", last_dir)
            if where is not None:
                where = os.path.expanduser(where.strip() or last_dir)
                if not Path(where).is_dir():
                    error_pause(stdscr, f"no such directory: {where}")
                else:
                    last_dir = where
                    task = compose(stdscr, where)
                    if not task:
                        flash(stdscr, " cancelled — nothing written")
                    else:
                        flash(stdscr, " starting instance…")
                        try:
                            rec = ocore.new_instance(task, directory=where)
                            flash(stdscr, f" started "
                                  f"{rec.get('ticket') or rec['session_id'][-8:]}", C_OK)
                        except Exception as e:
                            error_pause(stdscr, f"failed: {e}")
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
        elif ch == "d" and cur:
            label = cur.get("ticket") or ocore._headline(cur)[:40]
            if confirm(stdscr, f" remove “{label}” from the dashboard?"):
                ocore.remove_instance(cur["session_id"])
                data.refresh_now()
        elif ch == "r" and cur:
            name = ask(stdscr, " title:", ocore._headline(cur))
            if name:
                try:
                    ocore.rename_instance(cur["session_id"], name)
                    flash(stdscr, " renamed", C_OK)
                except Exception as e:
                    error_pause(stdscr, f"failed: {e}")
                data.refresh_now()
        elif ch == "R":
            data.refresh_now()
            flash(stdscr, " refreshing…")
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
    if err:
        error_pause(stdscr, err)
    data.refresh_now()


def main() -> int:
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print("opendash: the dashboard needs a terminal "
              "(try `opendash list` when piping output)", file=sys.stderr)
        return 2
    if not os.environ.get("TERM"):
        os.environ["TERM"] = "xterm-256color"
    start_dir = os.getcwd()
    try:
        ocore.server_url()
    except ocore.ApiError as e:
        print(f"opendash: cannot start opencode server: {e}")
        return 1
    curses.wrapper(run, start_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
