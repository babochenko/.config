#!/usr/bin/env python3
"""
opendash core -- background opencode instances.

An "instance" is an opencode session hosted by one shared headless
`opencode serve` process. The server is detached from the shell, so work keeps
running after the terminal (and the dashboard) is closed. Live state is read
straight out of opencode's own sqlite db; actions go over the server's HTTP API.

Stdlib only, no install step.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------- paths/config

HERE = Path(__file__).resolve().parent
STATE = Path(os.environ.get("OPENDASH_STATE", Path.home() / ".local/state/opendash"))
INSTANCES = STATE / "instances"
SERVER_JSON = STATE / "server.json"
SERVER_LOG = STATE / "server.log"
JIRA_CACHE = STATE / "jira.json"
TMUX_CONF = STATE / "tmux.conf"
TMUX_SOCKET = os.environ.get("OPENDASH_TMUX_SOCKET", "opendash")

CONFIG_PATHS = [
    Path(os.environ.get("OPENDASH_CONFIG", "")) if os.environ.get("OPENDASH_CONFIG") else None,
    Path.home() / ".config/opendash/config.json",
    HERE / "config.json",
]

READ_PERMISSION = json.dumps({
    k: "allow" for k in (
        "read", "glob", "grep", "list", "todowrite", "webfetch", "websearch",
        "lsp", "skill",
    )
})
AUTO_PERMISSION = json.dumps({
    k: "allow" for k in (
        "read", "edit", "glob", "grep", "list", "bash", "task",
        "external_directory", "todowrite", "webfetch", "websearch", "lsp", "skill",
    )
})


def permission_json() -> str:
    """Validated permissions for background instances.

    Instances are started the way `opencode --auto --agent myagent` would be, so
    tools are allowed up front -- nobody is watching to approve them. Set
    OPENDASH_AUTO=0 for read-only instances, or OPENDASH_PERMISSION to a JSON
    object for anything in between.
    """
    raw = os.environ.get("OPENDASH_PERMISSION")
    if raw is None:
        return READ_PERMISSION if os.environ.get("OPENDASH_AUTO") == "0" else AUTO_PERMISSION
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ApiError("OPENDASH_PERMISSION must be a JSON object") from e
    if not isinstance(value, dict):
        raise ApiError("OPENDASH_PERMISSION must be a JSON object")
    return raw


def _load_config() -> dict:
    cfg: dict = {}
    for p in CONFIG_PATHS:
        if p and p.is_file():
            try:
                cfg = json.loads(p.read_text()) or {}
                break
            except (json.JSONDecodeError, OSError):
                pass
    for key, env in (
        ("model", "OPENDASH_MODEL"),
        ("agent", "OPENDASH_AGENT"),
        ("jira_base_url", "JIRA_BASE_URL"),
        ("jira_email", "JIRA_EMAIL"),
        ("jira_api_token", "JIRA_API_TOKEN"),
    ):
        if os.environ.get(env):
            cfg[key] = os.environ[env]
    return cfg


CONFIG = _load_config()


def opencode_bin() -> str:
    return shutil.which("opencode") or str(Path.home() / ".opencode/bin/opencode")


def db_path() -> Path:
    if os.environ.get("OPENCODE_DB"):
        return Path(os.environ["OPENCODE_DB"])
    return Path.home() / ".local/share/opencode/opencode.db"


def _read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(path)


def now_ms() -> int:
    return int(time.time() * 1000)


# ------------------------------------------------------------------------ http


class ApiError(RuntimeError):
    pass


def http(url: str, method: str = "GET", body=None, timeout: float = 10.0):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"content-type": "application/json"} if data is not None else {}
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        raise ApiError(f"{method} {url} -> {e.code} {e.read()[:200].decode(errors='replace')}") from e
    except (urllib.error.URLError, socket.timeout, OSError) as e:
        raise ApiError(f"{method} {url} -> {e}") from e
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------- oc server

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _server_alive(url: str, timeout: float = 2.0) -> bool:
    try:
        http(f"{url}/session", timeout=timeout)
        return True
    except ApiError:
        return False


def server_info() -> dict | None:
    return _read_json(SERVER_JSON)


def _server_process_owned(info: dict) -> bool:
    """Avoid signaling a reused PID from stale server metadata."""
    pid = info.get("pid")
    if not pid:
        return False
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True, text=True, timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    command = result.stdout.strip()
    return result.returncode == 0 and "serve" in command and "opencode" in command


def server_url(start: bool = True) -> str | None:
    """URL of the shared headless opencode server, starting it if needed."""
    info = server_info()
    if (info and info.get("url") and _server_process_owned(info)
            and _server_alive(info["url"])):
        return info["url"]
    if not start:
        return None
    return _start_server()


def _start_server() -> str:
    STATE.mkdir(parents=True, exist_ok=True)
    port = _free_port()
    env = os.environ.copy()
    env.setdefault("OPENCODE_PERMISSION", permission_json())
    with open(SERVER_LOG, "ab") as log:
        log.write(f"\n=== opendash starting server on :{port} at {time.ctime()} ===\n".encode())
        log.flush()
        proc = subprocess.Popen(
            [opencode_bin(), "serve", "--port", str(port), "--hostname", "127.0.0.1"],
            stdout=log, stderr=log, stdin=subprocess.DEVNULL,
            start_new_session=True, env=env, cwd=str(Path.home()),
        )
    url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 45
    while time.time() < deadline:
        if proc.poll() is not None:
            raise ApiError(f"opencode serve exited ({proc.returncode}); see {SERVER_LOG}")
        if _server_alive(url, timeout=1.0):
            _write_json(SERVER_JSON, {"url": url, "port": port, "pid": proc.pid, "started": now_ms()})
            return url
        time.sleep(0.3)
    proc.terminate()
    raise ApiError(f"opencode serve did not come up on {url}; see {SERVER_LOG}")


def stop_server() -> bool:
    info = server_info()
    if not info:
        return False
    pid = info.get("pid")
    if pid and _server_process_owned(info):
        try:
            os.kill(pid, 15)
        except (ProcessLookupError, PermissionError):
            pass
    SERVER_JSON.unlink(missing_ok=True)
    return True


# --------------------------------------------------------------------- tickets

TICKET_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,9}-\d+)\b")
URL_TICKET_RE = re.compile(r"(?:/browse/|selectedIssue=|/issues/)([A-Za-z][A-Za-z0-9]{1,9}-\d+)")


def extract_ticket(text: str) -> str | None:
    if not text:
        return None
    m = URL_TICKET_RE.search(text)
    if m:
        return m.group(1).upper()
    m = TICKET_RE.search(text)
    return m.group(1) if m else None


# ------------------------------------------------------------------- instances


def instance_records() -> list[dict]:
    if not INSTANCES.is_dir():
        return []
    out = []
    for f in INSTANCES.glob("*.json"):
        rec = _read_json(f)
        if rec and rec.get("session_id"):
            rec["_file"] = str(f)
            out.append(rec)
    return out


def _split_model(model: str | None):
    if not model or "/" not in model:
        return None
    provider, _, mid = model.partition("/")
    return {"providerID": provider, "modelID": mid}


def send_prompt(session_id: str, text: str, directory: str,
                model: str | None = None, agent: str | None = None) -> None:
    """Append a message to a session and let the server work on it.

    model/agent are sent only when given. Naming a model in a prompt *switches*
    the session to it, so follow-ups pass neither and leave the session on
    whatever model and agent it is currently using -- including a switch made
    by hand inside the opencode TUI. Defaults are resolved once, at creation.
    """
    url = server_url()
    body: dict = {"parts": [{"type": "text", "text": text}]}
    m = _split_model(model)
    if m:
        body["model"] = m
    if agent:
        body["agent"] = agent
    q = urllib.parse.urlencode({"directory": directory})
    http(f"{url}/session/{session_id}/prompt_async?{q}", "POST", body, timeout=20)


def new_instance(task: str, ticket: str | None = None, directory: str | None = None,
                 model: str | None = None, agent: str | None = None) -> dict:
    url = server_url()
    directory = str(Path(directory or os.getcwd()).expanduser().resolve())
    q = urllib.parse.urlencode({"directory": directory})
    session = http(f"{url}/session?{q}", "POST", {}, timeout=20)
    if not session or not session.get("id"):
        raise ApiError("server did not return a session")
    sid = session["id"]
    rec = {
        "session_id": sid,
        "ticket": (ticket or extract_ticket(task) or "").upper() or None,
        "task": task,
        "directory": directory,
        "model": model or CONFIG.get("model"),
        "agent": agent or CONFIG.get("agent"),
        "created": now_ms(),
    }
    record_path = INSTANCES / f"{sid}.json"
    _write_json(record_path, rec)
    try:
        send_prompt(sid, task, directory, rec["model"], rec["agent"])
    except Exception:
        abort_instance(sid)
        record_path.unlink(missing_ok=True)
        raise
    return rec


def rename_instance(session_id: str, title: str) -> None:
    """Give an instance a name of your own.

    The ticket lives in our own record and is left alone -- it has its own
    column in the dashboard, so only the description changes.

    The name is kept locally *and* pushed to opencode, so it survives whatever
    opencode would have generated for the session title and also shows up in
    opencode's own session list.
    """
    title = " ".join(title.split())
    if not title:
        return
    path = INSTANCES / f"{session_id}.json"
    rec = _read_json(path)
    if rec:
        rec["title_override"] = title
        _write_json(path, rec)
    url = server_url(start=False)
    if not url:
        return
    q = urllib.parse.urlencode({"directory": (rec or {}).get("directory") or str(Path.home())})
    try:
        http(f"{url}/session/{session_id}?{q}", "PATCH", {"title": title}, timeout=8)
    except ApiError:
        pass                      # the local name still applies


def abort_instance(session_id: str) -> None:
    url = server_url(start=False)
    if not url:
        return
    try:
        http(f"{url}/session/{session_id}/abort", "POST", {}, timeout=5)
    except ApiError:
        pass


def quit_all() -> int:
    """Quit for real: stop every instance and the shared server.

    Instance records are kept, so reopening the dashboard still lists the work
    (idle, with its conversation intact) -- use `d` to drop one for good.
    """
    records = instance_records()
    for rec in records:
        abort_instance(rec["session_id"])
    tmux("kill-server")
    stop_server()
    return len(records)


def remove_instance(session_id: str) -> None:
    """Stop the run and drop it from the dashboard. The opencode session itself
    is kept, so the conversation stays available in opencode's history."""
    abort_instance(session_id)
    tmux_kill(session_id)
    (INSTANCES / f"{session_id}.json").unlink(missing_ok=True)


# ------------------------------------------------------------------ db reading

_IDLE_TITLE_RE = re.compile(r"^New session - \d{4}-")


def _connect():
    p = db_path()
    if not p.exists():
        raise ApiError(f"opencode db not found at {p}")
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=2.0)
    con.execute("pragma busy_timeout=2000")
    return con


def _tool_target(tool: str, inp: dict) -> str:
    if not isinstance(inp, dict):
        return tool
    for key in ("filePath", "path", "file"):
        if inp.get(key):
            return f"{tool} {Path(str(inp[key])).name}"
    if inp.get("command"):
        return f"{tool} {' '.join(str(inp['command']).split())[:60]}"
    for key in ("pattern", "query", "url", "description", "prompt", "subagent_type"):
        if inp.get(key):
            return f"{tool} {' '.join(str(inp[key]).split())[:60]}"
    return tool


def _activity(parts: list[tuple[str, int]]) -> tuple[str, str]:
    """Newest-first parts -> (kind, text) describing what the agent is up to."""
    running = None
    last_tool = None
    last_text = None
    for raw, _ts in parts:
        try:
            d = json.loads(raw)
        except json.JSONDecodeError:
            continue
        t = d.get("type")
        if t == "tool":
            status = (d.get("state") or {}).get("status")
            target = _tool_target(d.get("tool", "tool"), (d.get("state") or {}).get("input"))
            if status in ("running", "pending") and running is None:
                running = target
            elif last_tool is None:
                last_tool = target
        elif t == "text" and d.get("text") and last_text is None:
            first = next((ln.strip() for ln in str(d["text"]).splitlines() if ln.strip()), "")
            if first:
                last_text = first
    if running:
        return "running", running
    if last_text:
        return "said", last_text
    if last_tool:
        return "tool", last_tool
    return "none", ""


def snapshot(records: list[dict]) -> list[dict]:
    """Join instance records with live opencode state. Never raises on db hiccups."""
    if not records:
        return []
    try:
        con = _connect()
    except ApiError:
        return [dict(r, state="unknown", title=None, todos=[], activity=("none", "")) for r in records]

    out = []
    try:
        for rec in records:
            sid = rec["session_id"]
            item = dict(rec)
            row = con.execute(
                "select title, cost, tokens_input, tokens_output, summary_additions,"
                " summary_deletions, summary_files, time_created, time_updated, model, agent"
                " from session where id = ?", (sid,)
            ).fetchone()
            if row:
                (title, cost, tin, tout, adds, dels, files,
                 t_created, t_updated, model_json, agent) = row
                item.update(
                    title=None if not title or _IDLE_TITLE_RE.match(title) else title,
                    cost=cost or 0.0, tokens_in=tin or 0, tokens_out=tout or 0,
                    adds=adds or 0, dels=dels or 0, files=files or 0,
                    time_created=t_created, time_updated=t_updated, agent_live=agent,
                )
                if model_json:
                    try:
                        m = json.loads(model_json)
                        item["model_live"] = f"{m.get('providerID')}/{m.get('id') or m.get('modelID')}"
                    except json.JSONDecodeError:
                        pass
                item["exists"] = True
            else:
                item.update(exists=False, title=None, cost=0.0, tokens_in=0, tokens_out=0,
                            adds=0, dels=0, files=0, time_updated=rec.get("created"))

            item["todos"] = [
                {"status": s, "content": c}
                for s, c in con.execute(
                    "select status, content from todo where session_id = ? order by position", (sid,)
                )
            ]

            last = con.execute(
                "select json_extract(data,'$.role'), json_extract(data,'$.time.completed'),"
                " json_extract(data,'$.error'), time_created"
                " from message where session_id = ? order by time_created desc, id desc limit 1",
                (sid,),
            ).fetchone()
            if not last:
                item["state"] = "queued"
                item["last_activity"] = item.get("time_updated") or rec.get("created")
            else:
                role, completed, error, msg_ts = last
                item["last_activity"] = msg_ts or item.get("time_updated")
                if error:
                    item["state"] = "error"
                    item["error"] = error if isinstance(error, str) else json.dumps(error)[:200]
                elif role == "user":
                    item["state"] = "queued"
                elif completed:
                    item["state"] = "idle"
                else:
                    item["state"] = "working"

            # only the assistant's own parts -- otherwise the newest "text"
            # part is the prompt we just sent, and line 2 echoes line 1
            if not item.get("exists", True):
                item["state"] = "unknown"      # session deleted out from under us

            item["activity"] = _activity(
                con.execute(
                    "select p.data, p.time_created from part p"
                    " join message m on m.id = p.message_id"
                    " where p.session_id = ?"
                    "   and json_extract(m.data,'$.role') = 'assistant'"
                    " order by p.time_created desc, p.id desc limit 25", (sid,)
                ).fetchall()
            )
            out.append(item)
    finally:
        con.close()

    return sort_items(out)


def order_key(rec: dict) -> float:
    """Where an instance sits in the list.

    Start time by default, so a new instance lands at the bottom. Moving one by
    hand swaps its key with its neighbour's, which keeps every key in the same
    numeric space -- no renumbering of the whole list, and the arrangement
    survives a restart because it lives in the instance record.
    """
    manual = rec.get("order")
    if isinstance(manual, (int, float)) and not isinstance(manual, bool):
        return float(manual)
    return float(rec.get("created") or rec.get("time_created") or 0)


def sort_items(items: list[dict]) -> list[dict]:
    """Start order, unless you have moved things around with J/K.

    Deliberately not ordered by state or activity: the list has to hold still
    while you navigate it, and a row that jumps as its agent works is a row you
    select by accident.
    """
    items.sort(key=lambda i: (order_key(i), i.get("session_id") or ""))
    return items


def move_instance(session_id: str, delta: int) -> bool:
    """Move an instance up (-1) or down (+1) the list. False if it cannot."""
    records = sorted(instance_records(), key=order_key)
    index = next((n for n, r in enumerate(records)
                  if r["session_id"] == session_id), None)
    if index is None:
        return False
    target = index + delta
    if not 0 <= target < len(records):
        return False
    keys = [order_key(records[index]), order_key(records[target])]
    for rec, key in ((records[index], keys[1]), (records[target], keys[0])):
        path = INSTANCES / f"{rec['session_id']}.json"
        stored = _read_json(path)
        if stored is None:
            return False
        stored["order"] = key
        _write_json(path, stored)
    return True


def pending_attention(items: list[dict]) -> dict[str, str]:
    """{session_id: label} for instances blocked waiting on you.

    opencode scopes pending permission requests by directory, so ask once per
    distinct instance directory rather than once per session.
    """
    info = server_info()
    url = info.get("url") if info else None
    if not url or not items:
        return {}
    out: dict[str, str] = {}
    for directory in {i.get("directory") for i in items if i.get("directory")}:
        q = urllib.parse.urlencode({"directory": directory})
        try:
            requests = http(f"{url}/permission?{q}", timeout=3) or []
        except ApiError:
            continue
        for req in requests if isinstance(requests, list) else []:
            sid = req.get("sessionID")
            if not sid:
                continue
            tool = req.get("permission") or "permission"
            detail = (req.get("metadata") or {}).get("command") or ""
            if not detail:
                patterns = req.get("patterns") or []
                detail = str(patterns[0]) if patterns else ""
            out[sid] = " ".join(f"{tool} {detail}".split())[:80]

    # the question tool blocks the same way, when it is enabled
    for item in items:
        sid = item["session_id"]
        if sid in out or item.get("state") != "working":
            continue
        q = urllib.parse.urlencode({"directory": item.get("directory") or ""})
        try:
            data = http(f"{url}/api/session/{sid}/question?{q}", timeout=3)
        except ApiError:
            continue
        asked = (data or {}).get("data") if isinstance(data, dict) else data
        if asked:
            first = asked[0] if isinstance(asked, list) else asked
            text = ""
            if isinstance(first, dict):
                text = str(first.get("question") or first.get("text") or "")
            out[sid] = " ".join(f"question {text}".split())[:80]
    return out


# ------------------------------------------------------------------------ jira

_STATUS_CATEGORY = {"new": "todo", "indeterminate": "progress", "done": "done"}


def jira_config() -> tuple[str, str, str] | None:
    base = CONFIG.get("jira_base_url")
    email = CONFIG.get("jira_email")
    token = CONFIG.get("jira_api_token")
    if not token:
        try:
            token = subprocess.run(
                ["security", "find-generic-password", "-s", "jira-api-token", "-w"],
                capture_output=True, text=True, timeout=5,
            ).stdout.strip() or None
        except (OSError, subprocess.SubprocessError):
            token = None
    if base and email and token:
        return base.rstrip("/"), email, token
    return None


def jira_cache() -> dict:
    return _read_json(JIRA_CACHE, {}) or {}


def jira_refresh(tickets: list[str], ttl: float = 300.0) -> dict:
    """Fetch status for tickets, caching to disk. No creds -> returns cache as-is."""
    cache = jira_cache()
    conf = jira_config()
    if not conf:
        return cache
    base, email, token = conf
    auth = base64.b64encode(f"{email}:{token}".encode()).decode()
    stale = [t for t in tickets if time.time() - (cache.get(t, {}).get("fetched", 0)) > ttl]
    for key in stale:
        req = urllib.request.Request(
            f"{base}/rest/api/3/issue/{urllib.parse.quote(key)}?fields=status,summary",
            headers={"authorization": f"Basic {auth}", "accept": "application/json"},
        )
        entry: dict = {"fetched": time.time()}
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                fields = (json.loads(resp.read()) or {}).get("fields", {})
            status = fields.get("status") or {}
            entry["status"] = status.get("name")
            entry["category"] = _STATUS_CATEGORY.get(
                (status.get("statusCategory") or {}).get("key", ""), "todo")
            entry["summary"] = fields.get("summary")
        except urllib.error.HTTPError as e:
            entry["error"] = f"HTTP {e.code}"
        except (urllib.error.URLError, socket.timeout, OSError, json.JSONDecodeError) as e:
            entry["error"] = str(e)[:80]
        cache[key] = entry
    if stale:
        _write_json(JIRA_CACHE, cache)
    return cache


# ------------------------------------------------------------------------ tmux

# option+q closes a `t` terminal only when its prompt is idle, and detaches
# from anything else -- an opencode TUI, or a terminal with a build running.
# The test lives in a shell script because it has to compare pids: see the
# comments in idle-check.sh for why a process-name test is not good enough.
IDLE_CHECK = HERE / "idle-check.sh"


def _tmux_conf() -> Path:
    """Config for our private tmux server.

    option+q leaves an instance. If the pane is an idle shell (the `t`
    terminal with nothing running) the session is closed outright; if anything
    is actually running -- an opencode TUI, a build -- it only detaches, so the
    work survives. macOS sends option+q either as M-q (with
    `macos-option-as-alt`) or as the literal "oe" ligature, so both are bound.
    """
    check = IDLE_CHECK
    args = '"#{session_name}" "#{pane_tty}" "#{pane_pid}"'
    leave = f"if-shell '{check} {args}' 'kill-session' 'detach-client'"
    body = f"""
set -g status on
set -g status-position bottom
set -g status-justify left
set -g status-style "bg=#1c1c1c,fg=#767676"
set -g status-left ""
set -g status-right ""
set -g escape-time 10
set -g focus-events on
set -g history-limit 50000
set -g destroy-unattached off
set -g detach-on-destroy on
set -ga terminal-features ",*:RGB"
set -g window-status-format ""
set -g window-status-current-format ""
bind-key -n M-q {leave}
bind-key -n œ {leave}
"""
    STATE.mkdir(parents=True, exist_ok=True)
    if not TMUX_CONF.exists() or TMUX_CONF.read_text() != body:
        TMUX_CONF.write_text(body)
    _sync_running_server()
    return TMUX_CONF


_CONF_SYNCED = False


def _sync_running_server() -> None:
    """Push the current bindings onto a tmux server that is already up.

    tmux only reads its config when the server starts, so a server left over
    from an older opendash keeps whatever bindings it started with -- which is
    how a fixed option+q can appear not to be fixed. Sourcing the config makes
    it self-healing instead of needing every view closed first.
    """
    global _CONF_SYNCED
    if _CONF_SYNCED:
        return
    _CONF_SYNCED = True
    subprocess.run(["tmux", "-L", TMUX_SOCKET, "source-file", str(TMUX_CONF)],
                   capture_output=True, text=True, env=_tmux_env())


def _tmux_env() -> dict:
    """tmux refuses to attach from inside another tmux while $TMUX is set, so
    the dashboard still works when it is itself running in a tmux pane."""
    env = os.environ.copy()
    env.pop("TMUX", None)
    env.pop("TMUX_PANE", None)
    return env


def tmux(*args: str, check: bool = False, capture: bool = True):
    cmd = ["tmux", "-L", TMUX_SOCKET, "-f", str(_tmux_conf()), *args]
    return subprocess.run(cmd, capture_output=capture, text=True,
                          check=check, env=_tmux_env())


def tmux_name(session_id: str, kind: str = "oc") -> str:
    """kind "oc" is the opencode TUI, "sh" is the plain terminal."""
    return f"{kind}-{session_id[-8:]}"


def tmux_exists(session_id: str, kind: str = "oc") -> bool:
    return tmux("has-session", "-t", f"={tmux_name(session_id, kind)}").returncode == 0


def tmux_kill(session_id: str) -> None:
    for kind in ("oc", "sh"):
        tmux("kill-session", "-t", f"={tmux_name(session_id, kind)}")


def _decorate(name: str, label: str, hint: str) -> None:
    # note: set-option does not accept the "=exact" target prefix that
    # has-session/attach-session/kill-session take, so pass the bare name
    for opt, val in (
        ("status-left", f" #[bold]{label}#[default] "),
        ("status-left-length", "160"),
        ("status-right", f" {hint} "),
        ("status-right-length", "48"),
    ):
        tmux("set-option", "-t", name, opt, val)


_SHELL_NAMES = ("sh", "bash", "zsh", "dash", "ksh", "fish", "csh", "tcsh")


def _is_shell_name(name: str) -> bool:
    return name in _SHELL_NAMES or name.endswith("sh")


def terminal_activity(items: list[dict]) -> dict[str, str]:
    """{session_id: command} for instances with a `t` terminal open.

    The command is "" when the terminal is idle, and an instance with no
    terminal at all is simply absent from the result.

    One tmux call covers every instance, and ps is only consulted when there
    are terminals open at all.
    """
    names = {tmux_name(i["session_id"], "sh"): i["session_id"] for i in items}
    if not names:
        return {}
    listing = tmux("list-panes", "-a", "-F",
                   "#{session_name}\t#{pane_tty}\t#{pane_pid}")
    if listing.returncode != 0:
        return {}
    panes: dict[str, tuple[str, int]] = {}       # tty -> (session id, shell pid)
    for line in listing.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        name, tty, shell_pid = parts
        session_id = names.get(name)
        if session_id and shell_pid.isdigit():
            panes[tty.rsplit("/", 1)[-1]] = (session_id, int(shell_pid))
    if not panes:
        return {}
    jobs = _foreground_jobs({tty: pid for tty, (_, pid) in panes.items()})
    # every open terminal is reported; "" means it is sitting at an idle prompt
    return {sid: jobs.get(tty, "") for tty, (sid, _) in panes.items()}


def _foreground_jobs(panes: dict[str, int]) -> dict[str, str]:
    """tty -> the foreground job's command, for panes that are not idle.

    Same pid-based rule as idle-check.sh, and for the same reason: a pane
    running ./gradlew reports its current command as "bash", so a name test
    would call a busy terminal idle.
    """
    try:
        out = subprocess.run(["ps", "-o", "tty=,pid=,pgid=,stat=,args=", "-A"],
                             capture_output=True, text=True, timeout=4).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    found: dict[str, str] = {}
    for line in out.splitlines():
        parts = line.split(None, 4)
        if len(parts) < 5:
            continue
        tty, pid, pgid, stat, args = parts
        shell_pid = panes.get(tty)
        if shell_pid is None or "+" not in stat:      # "+" is the foreground group
            continue
        if not (pid.isdigit() and pgid.isdigit()) or int(pid) == shell_pid:
            continue
        # the group leader is what was typed; anything else it spawned is detail
        if pid == pgid or tty not in found:
            found[tty] = _typed_command(args)
    return found


def _typed_command(args: str) -> str:
    argv = args.split()
    if not argv:
        return ""
    if _is_shell_name(Path(argv[0]).name) and len(argv) > 1:
        argv = argv[1:]              # "/bin/sh ./gradlew test" -> "./gradlew test"
    return " ".join([Path(argv[0]).name] + argv[1:])


def attach(item: dict) -> None:
    """Open the instance's opencode TUI. Blocks until option+q / detach."""
    url = server_url()
    sid = item["session_id"]
    name = tmux_name(sid)
    directory = item.get("directory") or str(Path.home())
    # a window from before a server restart still points at the dead port
    if tmux_exists(sid) and _session_url(name) != url:
        tmux("kill-session", "-t", f"={name}")
    if not tmux_exists(sid):
        # a fast exit means it failed (bad config, server gone); hold the pane
        # so the error is readable instead of flashing back to the dashboard
        inner = (
            'start=$(date +%s); '
            f'{_sh_quote(opencode_bin())} attach {_sh_quote(url)} '
            f'--session {_sh_quote(sid)} --dir {_sh_quote(directory)}; '
            'rc=$?; '
            'if [ $rc -ne 0 ] || [ $(( $(date +%s) - start )) -lt 3 ]; then '
            'printf "\\n opencode attach exited (%s) - press enter to return to '
            'the dashboard " "$rc"; read -r _; fi'
        )
        r = tmux("new-session", "-d", "-s", name, "-c", directory, "sh", "-c", inner)
        if r.returncode != 0:
            raise ApiError(f"tmux: {(r.stderr or '').strip() or 'could not create session'}")
        tmux("set-option", "-t", name, "@opendash_url", url)
        _decorate(name, _label(item), "option+q → dashboard")
    _tmux_attach(name)


def attach_terminal(item: dict) -> None:
    """Open a plain shell in the instance's working directory.

    option+q closes it when the prompt is idle and just detaches when something
    is still running, so a long build is never killed by accident.
    """
    sid = item["session_id"]
    name = tmux_name(sid, "sh")
    directory = item.get("directory") or str(Path.home())
    if not tmux_exists(sid, "sh"):
        r = tmux("new-session", "-d", "-s", name, "-c", directory)
        if r.returncode != 0:
            raise ApiError(f"tmux: {(r.stderr or '').strip() or 'could not create session'}")
        _decorate(name, f"{_label(item)}  ·  {Path(directory).name}",
                  "option+q → close (detaches if busy)")
    _tmux_attach(name)


def _session_url(name: str) -> str | None:
    r = tmux("show-options", "-v", "-t", name, "@opendash_url")
    return r.stdout.strip() or None if r.returncode == 0 else None


def _tmux_attach(name: str) -> None:
    subprocess.run(
        ["tmux", "-L", TMUX_SOCKET, "-f", str(_tmux_conf()), "attach-session", "-t", f"={name}"],
        env=_tmux_env(),
    )


def _label(item: dict) -> str:
    return " ".join(x for x in (item.get("ticket"), _headline(item)) if x)[:70]


def _sh_quote(s: str) -> str:
    return "'" + str(s).replace("'", "'\\''") + "'"


# ---------------------------------------------------------------- presentation

def _strip_ticket(text: str, ticket: str | None) -> str:
    """The ticket has its own column, so drop it from the headline."""
    if not ticket:
        return text
    if text.upper().startswith(ticket):
        text = text[len(ticket):]
    return text.lstrip(" :-–—\u2022")


def _headline(item: dict) -> str:
    """Line 1 text: opencode's own generated title, else the task we sent."""
    ticket = item.get("ticket")
    # a name you set by hand wins over the one opencode generated
    for title in (item.get("title_override"), item.get("title")):
        if title:
            return _strip_ticket(" ".join(str(title).split()), ticket) or str(title)
    # tasks are written in an editor and are often several lines; until
    # opencode has generated its own title, show just the first line
    task = str(item.get("task") or "")
    first = next((ln.strip() for ln in task.splitlines() if ln.strip()), "")
    return _strip_ticket(" ".join(first.split()), ticket) or "(no task)"


def _progress(item: dict) -> str:
    todos = item.get("todos") or []
    if not todos:
        return ""
    done = sum(1 for t in todos if t["status"] == "completed")
    return f"✓{done}/{len(todos)}"


def worked_on(item: dict) -> str:
    """Line 2 text: what the instance has actually been doing."""
    todos = item.get("todos") or []
    current = next((t["content"] for t in todos if t["status"] == "in_progress"), None)
    kind, text = item.get("activity", ("none", ""))
    if item.get("state") == "working":
        if kind == "running" and text:
            return f"{text}" if not current else f"{current} — {text}"
        if current:
            return current
        if text:
            return text
        return "thinking…"
    if item.get("state") == "error":
        return item.get("error") or "run failed"
    if item.get("state") == "queued":
        return "queued — waiting for the model"
    if kind == "said" and text:
        return text
    if current:
        return current
    if text:
        return text
    return "no output yet"


def fmt_age(ms: int | None) -> str:
    if not ms:
        return ""
    secs = max(0, int(time.time() - ms / 1000))
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        return f"{secs // 60}m"
    if secs < 86400:
        return f"{secs // 3600}h{(secs % 3600) // 60:02d}"
    return f"{secs // 86400}d"


# ------------------------------------------------------------------------- cli

def _cmd_new(args) -> int:
    task = " ".join(args.task).strip()
    if not task:
        print("opendash new: need a task description", file=sys.stderr)
        return 2
    rec = new_instance(task, ticket=args.ticket, directory=args.dir,
                       model=args.model, agent=args.agent)
    print(f"{rec['session_id']}  {rec.get('ticket') or '-'}  {rec['directory']}")
    return 0


def _cmd_list(args) -> int:
    items = snapshot(instance_records())
    if not items:
        print("no instances")
        return 0
    for i in items:
        print(f"{i['state']:<8} {i.get('ticket') or '-':<12} {_headline(i)[:60]:<60} "
              f"{_progress(i):<8} {fmt_age(i.get('last_activity'))}")
        print(f"{'':<8} {'':<12} {worked_on(i)[:60]}")
    return 0


def _cmd_rm(args) -> int:
    for sid in args.session_id:
        remove_instance(sid)
        print(f"removed {sid}")
    return 0


def _cmd_abort(args) -> int:
    for sid in args.session_id:
        abort_instance(sid)
        print(f"aborted {sid}")
    return 0


def _cmd_quit(args) -> int:
    print(f"stopped {quit_all()} instance(s) and the shared server")
    return 0


def _cmd_server(args) -> int:
    if args.action == "start":
        print(server_url())
    elif args.action == "stop":
        print("stopped" if stop_server() else "no server recorded")
    else:
        info = server_info()
        if info and _server_process_owned(info) and _server_alive(info["url"]):
            print(f"up   {info['url']}  pid={info.get('pid')}")
        else:
            print("down")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="opendash", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("new", help="start a background instance")
    p.add_argument("task", nargs="+")
    p.add_argument("-t", "--ticket")
    p.add_argument("-d", "--dir")
    p.add_argument("-m", "--model")
    p.add_argument("--agent")
    p.set_defaults(fn=_cmd_new)

    p = sub.add_parser("list", help="list instances")
    p.set_defaults(fn=_cmd_list)

    p = sub.add_parser("rm", help="stop and forget instances")
    p.add_argument("session_id", nargs="+")
    p.set_defaults(fn=_cmd_rm)

    p = sub.add_parser("abort", help="interrupt a running instance")
    p.add_argument("session_id", nargs="+")
    p.set_defaults(fn=_cmd_abort)

    p = sub.add_parser("quit", help="stop every instance and the shared server")
    p.set_defaults(fn=_cmd_quit)

    p = sub.add_parser("server", help="manage the shared opencode server")
    p.add_argument("action", nargs="?", default="status",
                   choices=["status", "start", "stop"])
    p.set_defaults(fn=_cmd_server)

    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except ApiError as e:
        print(f"opendash: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
