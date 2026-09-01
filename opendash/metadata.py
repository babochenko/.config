"""OpenDash associations discovered from OpenCode conversations.

This module deliberately contains scanning and provider data shaping only.  The
dashboard consumes its small dictionaries and does not know about SQLite.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

TICKET_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,9}-\d+)\b")
URL_TICKET_RE = re.compile(r"(?:/browse/|selectedIssue=|/issues/)([A-Za-z][A-Za-z0-9]{1,9}-\d+)", re.I)
PR_URL_RE = re.compile(r"https?://[^\s)>]+/(?:pull-requests|pullrequests)/([0-9]+)", re.I)
PR_REF_RE = re.compile(r"\b(?:PR|pull\s+request|pullrequest)\s*#?\s*([0-9]+)\b", re.I)
DEFAULT_REFRESH = 45.0
AGENT_TIMEOUT = 30.0


def extract_tickets(text: str) -> list[str]:
    if not text:
        return []
    # URLs are checked first because prose may contain a different ticket too.
    found = [m.group(1).upper() for m in URL_TICKET_RE.finditer(text)]
    found.extend(m.group(1).upper() for m in TICKET_RE.finditer(text))
    return list(dict.fromkeys(found))


def extract_ticket(text: str) -> str | None:
    values = extract_tickets(text)
    return values[0] if values else None


def extract_prs(text: str) -> list[dict]:
    if not text:
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for match in PR_URL_RE.finditer(text):
        number = match.group(1)
        if number not in seen:
            out.append({"number": number, "label": f"#{number}", "url": match.group(0).rstrip(".,")})
            seen.add(number)
    for match in PR_REF_RE.finditer(text):
        number = match.group(1)
        if number not in seen:
            out.append({"number": number, "label": f"#{number}"})
            seen.add(number)
    return out


def _repository_from_pr_url(url: str | None) -> str | None:
    if not url:
        return None
    try:
        parts = urllib.parse.urlsplit(url).path.strip("/").split("/")
        marker = next((i for i, part in enumerate(parts)
                       if part.lower() in ("pull-requests", "pullrequests")), -1)
        return "/".join(parts[:marker]) if marker > 1 else None
    except ValueError:
        return None


def _text(value) -> list[str]:
    """Extract text from message/part JSON without assuming one schema version."""
    if isinstance(value, dict):
        result = []
        if isinstance(value.get("text"), str):
            result.append(value["text"])
        for child in value.values():
            if isinstance(child, (dict, list)):
                result.extend(_text(child))
        return result
    if isinstance(value, list):
        result = []
        for child in value:
            result.extend(_text(child))
        return result
    return []


def conversation_text(con, session_id: str) -> str:
    chunks: list[str] = []
    rows = con.execute("select data from message where session_id = ?", (session_id,))
    for (raw,) in rows:
        try:
            chunks.extend(_text(json.loads(raw)))
        except (TypeError, json.JSONDecodeError):
            pass
    rows = con.execute("select data from part where session_id = ?", (session_id,))
    for (raw,) in rows:
        try:
            chunks.extend(_text(json.loads(raw)))
        except (TypeError, json.JSONDecodeError):
            pass
    return "\n".join(chunks)


def scan_session(con, session_id: str, ignored: dict | None = None, repository_path: str | None = None,
                scan_prs: bool = True) -> dict:
    text = conversation_text(con, session_id)
    tickets = extract_tickets(text)
    prs = extract_prs(text) if scan_prs else []
    ignored = ignored or {}
    ignored_tickets = {str(v).upper() for v in ignored.get("tickets", [])}
    ignored_prs = {str(v).lstrip("#") for v in ignored.get("prs", [])}
    tickets = [t for t in tickets if t not in ignored_tickets]
    prs = [p for p in prs if p["number"] not in ignored_prs]
    for pr in prs:
        pr.setdefault("repository", _repository_from_pr_url(pr.get("url")))
    if repository_path:
        for pr in prs:
            pr.setdefault("repository", repository_path)
            pr.setdefault("url", f"https://bitbucket.org/{repository_path}/pull-requests/{pr['number']}")
    return {"tickets": tickets, "prs": prs}


def _candidate_key(candidate: dict) -> str:
    return f"{candidate.get('repository') or ''}#{candidate.get('number')}"


def _read(path: Path, default):
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, type(default)) else default
    except (OSError, json.JSONDecodeError):
        return default


def load(state: Path) -> dict:
    return _read(state / "metadata.json", {})


def save(state: Path, data: dict) -> None:
    state.mkdir(parents=True, exist_ok=True)
    path = state / "metadata.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(path)


def update(state: Path, con, records: list[dict]) -> dict:
    data = load(state)
    changed = False
    for record in records:
        sid = record["session_id"]
        entry = data.setdefault(sid, {})
        repository = os.environ.get("X_BITBUCKET_REPOSITORY")
        directory = str(record.get("directory") or "").rstrip("/").rsplit("/", 1)[-1]
        repository_path = f"{repository.strip('/')}/{directory}" if repository and directory else repository
        has_branch = bool(record.get("branch") or record.get("worktree"))
        found = scan_session(con, sid, entry.get("ignored"), repository_path, scan_prs=has_branch)
        if entry.get("tickets") != found["tickets"]:
            entry["tickets"] = found["tickets"]
            changed = True
        scanned_prs = {p["number"] for p in found["prs"]}
        existing_prs = entry.get("prs", [])
        merged = list(found["prs"])
        for pr in existing_prs:
            if pr["number"] not in scanned_prs:
                merged.append(pr)
        if entry.get("prs") != merged:
            entry["prs"] = merged
            changed = True
    if changed:
        save(state, data)
    return data


def unlink(state: Path, session_id: str, association: str | None = None) -> bool:
    data = load(state)
    entry = data.setdefault(session_id, {})
    ignored = entry.setdefault("ignored", {"tickets": [], "prs": []})
    changed = False
    if not association or ("-" in association and not association.lstrip("#").isdigit()):
        ticket = association.upper() if association else None
        if ticket and ticket not in ignored["tickets"]:
            ignored["tickets"].append(ticket); changed = True
        if not ticket:
            for value in entry.get("tickets", []):
                if value not in ignored["tickets"]: ignored["tickets"].append(value); changed = True
            entry["tickets"] = []
    else:
        number = association.lstrip("#")
        existing = [p for p in entry.get("prs", []) if p.get("number") != number]
        was_present = len(existing) < len(entry.get("prs", []))
        if was_present:
            entry["prs"] = existing
            if number not in ignored["prs"]:
                ignored["prs"].append(number)
            changed = True
    if changed:
        save(state, data)
    return changed


def _parse_association(association: str) -> str:
    """Normalise a ticket ID, PR ref (#123), or PR URL to a comparable key."""
    m = PR_URL_RE.search(association)
    if m:
        return m.group(1)
    return association.lstrip("#")


def link(state: Path, session_id: str, association: str) -> bool:
    data = load(state)
    entry = data.setdefault(session_id, {})
    ignored = entry.setdefault("ignored", {"tickets": [], "prs": []})
    changed = False
    if "-" in association and not association.lstrip("#").isdigit() and "://" not in association:
        ticket = association.upper()
        if ticket in ignored["tickets"]:
            ignored["tickets"].remove(ticket); changed = True
        tickets = entry.setdefault("tickets", [])
        if ticket not in tickets:
            tickets.insert(0, ticket); changed = True
    else:
        number = _parse_association(association)
        if number in ignored["prs"]:
            ignored["prs"].remove(number); changed = True
        prs = entry.setdefault("prs", [])
        if not any(p.get("number") == number for p in prs):
            label = f"#{number}"
            url = association if PR_URL_RE.search(association) else None
            pr = {"number": number, "label": label}
            if url:
                pr["url"] = url.rstrip(".,")
                pr["repository"] = _repository_from_pr_url(url)
            prs.append(pr); changed = True
    if changed:
        save(state, data)
    return changed


def associate_ticket(state: Path, session_id: str, ticket: str) -> bool:
    data = load(state)
    entry = data.setdefault(session_id, {})
    ignored = {str(v).upper() for v in entry.get("ignored", {}).get("tickets", [])}
    if ticket.upper() in ignored:
        return False
    tickets = entry.setdefault("tickets", [])
    if ticket.upper() in tickets:
        return False
    tickets.insert(0, ticket.upper())
    save(state, data)
    return True


def mcp_config() -> dict:
    """Configuration for the optional remote OpenCode/MCP metadata bridge."""
    file_config = {}
    config_paths = [os.environ.get("OPENDASH_CONFIG"),
                    str(Path.home() / ".config/opendash/config.json"),
                    str(Path(__file__).resolve().parent / "config.json")]
    for config_path in config_paths:
        if not config_path:
            continue
        try:
            value = json.loads(Path(config_path).read_text())
            file_config = value if isinstance(value, dict) else {}
            if file_config:
                break
        except (OSError, json.JSONDecodeError):
            continue
    def setting(env: str, key: str, default: str) -> str:
        return os.environ.get(env, str(file_config.get(key, default))).strip()
    try:
        timeout = float(os.environ.get("OPENDASH_MCP_TIMEOUT", "8"))
    except ValueError:
        timeout = 8.0
    try:
        refresh = float(setting("OPENDASH_METADATA_REFRESH", "metadata_refresh", str(DEFAULT_REFRESH)))
    except ValueError:
        refresh = DEFAULT_REFRESH
    return {
        "url": setting("OPENDASH_MCP_URL", "mcp_url", ""),
        "tool": setting("OPENDASH_MCP_TOOL", "mcp_tool", "opendash_metadata"),
        "agent": setting("OPENDASH_MCP_AGENT", "mcp_agent", ""),
        "directory": setting("OPENDASH_MCP_DIRECTORY", "mcp_directory", str(Path.home())),
        "timeout": timeout,
        "refresh": refresh,
        "provider": setting("OPENDASH_METADATA_PROVIDER", "metadata_provider", "agent"),
    }


def _post_json(url: str, body: dict, timeout: float) -> dict:
    request = urllib.request.Request(
        url, data=json.dumps(body).encode(), method="POST",
        headers={"accept": "application/json", "content-type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        value = json.loads(response.read() or b"{}")
    if not isinstance(value, dict):
        raise ValueError("bridge response must be a JSON object")
    return value


def _normalise_ticket(value: dict, ticket: str) -> dict:
    status = value.get("status")
    if isinstance(status, dict):
        status = status.get("name") or status.get("label")
    category = str(value.get("category") or value.get("status_category") or "todo").lower()
    category = {"new": "todo", "to do": "todo", "indeterminate": "progress",
                "in progress": "progress", "done": "done"}.get(category, category)
    return {"fetched": time.time(), "key": ticket, "status": status,
            "category": category, "url": value.get("url") or value.get("link"),
             "summary": value.get("summary"), "error": value.get("error")}


def _normalise_pr_status(value: dict) -> str | None:
    """Collapse provider lifecycle/review fields into dashboard states."""
    lifecycle = str(value.get("state") or value.get("lifecycle") or "").lower()
    review = str(value.get("review_status") or value.get("approval_status") or "").lower()
    if lifecycle in {"merged", "completed", "complete"}:
        return "merged"
    if lifecycle in {"declined", "rejected", "superseded"}:
        return "rejected"
    if review in {"needs_changes", "needs changes", "changes_requested", "requested_changes"}:
        return "needs changes"
    if review in {"approved", "approve"}:
        return "approved"
    if lifecycle in {"open", "opened", "active", "in progress", "in_progress"}:
        return "opened"
    raw_value = value.get("status")
    if isinstance(raw_value, dict):
        raw_value = raw_value.get("name") or raw_value.get("state")
    raw = str(raw_value or "").lower()
    return {
        "open": "opened", "opened": "opened", "approved": "approved",
        "needs_changes": "needs changes", "changes requested": "needs changes",
        "declined": "rejected", "rejected": "rejected", "merged": "merged",
    }.get(raw, raw or None)


def _normalise_pr(value: dict, candidate: dict) -> dict:
    approvals = value.get("approvals")
    builds = value.get("builds") if isinstance(value.get("builds"), dict) else {}
    comments = value.get("unresolved_comments") or []
    return {
        "fetched": time.time(), "number": str(value.get("number") or candidate.get("number")),
        "label": f"#{value.get('number') or candidate.get('number')}",
        "repository": candidate.get("repository"),
        "title": value.get("title"), "url": value.get("url") or value.get("link") or candidate.get("url"),
        "status": _normalise_pr_status(value),
        "approvals": approvals if isinstance(approvals, int) else None,
        "needs_update": bool(value.get("needs_update")),
        "unresolved_threads": int(value.get("unresolved_threads") or 0),
        "unresolved_comments": [comment for comment in comments if isinstance(comment, dict)],
        "builds": {"ok": int(builds.get("ok") or 0), "failed": int(builds.get("failed") or 0),
                   "unavailable": int(builds.get("unavailable") or 0),
                   "error": builds.get("error")},
        "tickets": [str(t).upper() for t in value.get("tickets", []) if isinstance(t, str)],
        "error": value.get("error"),
    }


def _cache(state: Path, name: str) -> dict:
    return _read(state / name, {}) or {}


def pr_cache(state: Path) -> dict:
    return _cache(state, "pr.json")


def jira_cache(state: Path) -> dict:
    return _cache(state, "jira.json")


def _write_cache(state: Path, name: str, value: dict) -> None:
    state.mkdir(parents=True, exist_ok=True)
    path = state / name
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2))
    tmp.replace(path)


def _json_response(text: str) -> dict | None:
    """Extract the first JSON object from an agent response."""
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text or ""):
        try:
            value, _ = decoder.raw_decode(text[match.start():])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def _agent_prompt(prs: list[dict]) -> str:
    candidates = json.dumps([
        {key: value for key, value in candidate.items()
         if key in ("number", "repository", "url")}
        for candidate in prs
    ], separators=(",", ":"))
    return (
        "Use the Bitbucket MCP tools only. Do not edit files, run shell commands, "
        "or perform any write operation. Fetch the current pull request status, "
        "approval count, whether updates are needed, unresolved review threads "
        "and comments, and build results for these candidates: " + candidates + "\n"
        "Return exactly one JSON object and no markdown in this schema: "
        '{"prs":[{"number":"123","repository":"team/project",'
        '"status":"opened","approvals":0,"needs_update":false,'
        '"unresolved_threads":0,"unresolved_comments":[],'
        '"builds":{"ok":0,"failed":0,"unavailable":0}}]}'
    )


def _refresh_via_agent(state: Path, prs: list[dict], conf: dict,
                       pull_requests: dict, ttl: float) -> None:
    """Ask a hidden read-only OpenCode session for Bitbucket PR metadata."""
    now = time.time()
    prs = [candidate for candidate in prs
           if now - float((pull_requests.get(_candidate_key(candidate)) or
                           pull_requests.get(str(candidate.get("number"))) or {})
                          .get("fetched", 0)) > ttl]
    if not prs:
        return
    try:
        # Lazy import avoids a metadata -> ocore -> metadata import cycle.
        import ocore
        url = ocore.server_url()
        session_path = state / "metadata-agent-session.json"
        session = _read(session_path, {})
        sid = session.get("id")
        if not sid:
            query = urllib.parse.urlencode({"directory": conf["directory"]})
            created = ocore.http(f"{url}/session?{query}", "POST", {}, timeout=20)
            sid = created.get("id") if isinstance(created, dict) else None
            if not sid:
                raise ValueError("metadata agent session was not created")
            _write_cache(state, "metadata-agent-session.json", {"id": sid})

        started = int(time.time() * 1000)
        ocore.send_prompt(sid, _agent_prompt(prs), conf["directory"],
                          agent=conf["agent"])
        deadline = time.monotonic() + AGENT_TIMEOUT
        response = None
        while time.monotonic() < deadline:
            response = ocore.latest_assistant_response(sid, started)
            if response and response[1]:
                break
            time.sleep(0.25)
        if not response or not response[1]:
            raise TimeoutError("metadata agent did not complete")
        result = _json_response(response[0])
        if not result or not isinstance(result.get("prs"), list):
            raise ValueError("metadata agent returned invalid JSON")
        candidates = {_candidate_key(candidate): candidate for candidate in prs}
        by_number = {str(candidate.get("number")): candidate for candidate in prs}
        for value in result["prs"]:
            if not isinstance(value, dict):
                continue
            candidate = candidates.get(_candidate_key(value)) or by_number.get(str(value.get("number")))
            if candidate:
                pull_requests[_candidate_key(candidate)] = _normalise_pr(value, candidate)
        _write_cache(state, "pr.json", pull_requests)
        ocore.prune_session_messages(sid)
    except (OSError, ValueError, TypeError, TimeoutError):
        # A provider outage must never erase the last known PR state.
        return


def refresh_remote(state: Path, tickets: list[str], prs: list[dict], ttl: float | None = None) -> tuple[dict, dict]:
    """Refresh only stale candidates through the documented MCP bridge.

    The bridge owns the MCP connection and must return ``tickets`` and ``prs``
    objects keyed by the requested candidates. No provider API is called here.
    An unavailable bridge leaves the previous cache intact and is non-fatal.
    """
    conf = mcp_config()
    jira, pull_requests = jira_cache(state), pr_cache(state)
    if not conf["url"]:
        if conf["provider"] == "agent":
            effective_ttl = conf["refresh"] if ttl is None else ttl
            _refresh_via_agent(state, prs, conf, pull_requests, effective_ttl)
        return jira, pull_requests
    ttl = conf["refresh"] if ttl is None else ttl
    now = time.time()
    ticket_candidates = [t for t in sorted(set(tickets))
                         if now - float(jira.get(t, {}).get("fetched", 0)) > ttl]
    pr_candidates = [p for p in prs
                     if now - float((pull_requests.get(_candidate_key(p)) or
                                     pull_requests.get(str(p.get("number"))) or {}).get("fetched", 0)) > ttl]
    if not ticket_candidates and not pr_candidates:
        return jira, pull_requests
    body = {"contract": "opendash-mcp-v1", "tool": conf["tool"], "read_only": True,
            "session": {"id": _cache(state, "mcp-session.json").get("id", "opendash-metadata"),
                        "reuse": True, "agent": conf["agent"],
                        "directory": conf["directory"]},
            "tickets": ticket_candidates, "prs": pr_candidates,
            "requirements": {"jira": ["status", "link"], "bitbucket": [
                "status", "link", "number", "approvals", "needs_update", "unresolved_threads",
                "builds_matching_changed_project"]}}
    try:
        result = _post_json(conf["url"], body, conf["timeout"])
        for ticket, value in (result.get("tickets") or {}).items():
            if ticket in ticket_candidates and isinstance(value, dict):
                jira[ticket] = _normalise_ticket(value, ticket)
        response_prs = result.get("prs") or []
        if isinstance(response_prs, dict):
            response_prs = [response_prs.get(_candidate_key(candidate)) or
                            response_prs.get(str(candidate.get("number"))) for candidate in pr_candidates]
        for candidate, value in zip(pr_candidates, response_prs):
            if isinstance(value, dict):
                pull_requests[_candidate_key(candidate)] = _normalise_pr(value, candidate)
        session = result.get("session")
        if isinstance(session, dict) and session.get("id"):
            _write_cache(state, "mcp-session.json", {"id": session["id"]})
        _write_cache(state, "jira.json", jira)
        _write_cache(state, "pr.json", pull_requests)
    except (OSError, ValueError, TypeError, TimeoutError) as error:
        # Keep stale data, but make the failure visible without blocking the UI.
        for candidate in pr_candidates:
            old = pull_requests.setdefault(_candidate_key(candidate), dict(candidate))
            old.setdefault("number", str(candidate.get("number")))
            old["error"] = str(error)[:120]
    return jira, pull_requests


def refresh_prs(state: Path, prs: list[dict], ttl: float = DEFAULT_REFRESH) -> dict:
    """Compatibility wrapper; PR data still goes exclusively through MCP."""
    return refresh_remote(state, [], prs, ttl)[1]
