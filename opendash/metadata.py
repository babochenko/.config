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
DEFAULT_REFRESH = 300.0
AGENT_TIMEOUT = 60.0
MAX_CONVERSATION_CHARS = 1_000_000
MAX_PROVIDER_BYTES = 4 * 1024 * 1024
MAX_PROVIDER_ITEMS = 100
MAX_PROVIDER_TEXT = 4000
AGENT_CONTROL = "metadata-agent-control.json"


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


def conversation_text(con, session_id: str, role: str | None = None) -> str:
    chunks: list[str] = []
    size = 0

    def add(value: str) -> bool:
        nonlocal size
        if size >= MAX_CONVERSATION_CHARS:
            return False
        value = value[:MAX_CONVERSATION_CHARS - size]
        chunks.append(value)
        size += len(value)
        return size < MAX_CONVERSATION_CHARS

    if role:
        rows = con.execute(
            "select data from message where session_id = ?"
            " and json_extract(data, '$.role') = ?", (session_id, role))
    else:
        rows = con.execute("select data from message where session_id = ?", (session_id,))
    for (raw,) in rows:
        try:
            if not all(add(value) for value in _text(json.loads(raw))):
                return "\n".join(chunks)
        except (TypeError, json.JSONDecodeError):
            pass
    query = "select p.data from part p join message m on m.id = p.message_id where p.session_id = ?"
    params: tuple = (session_id,)
    if role:
        query += " and json_extract(m.data, '$.role') = ?"
        params += (role,)
    rows = con.execute(query, params)
    for (raw,) in rows:
        try:
            if not all(add(value) for value in _text(json.loads(raw))):
                break
        except (TypeError, json.JSONDecodeError):
            pass
    return "\n".join(chunks)


def first_user_message_text(con, session_id: str) -> str:
    """Return only the first requested message, including its content parts."""
    row = con.execute(
        "select m.id, m.data from message m where m.session_id = ?"
        " and json_extract(m.data, '$.role') = 'user'"
        " order by m.time_created, m.id limit 1", (session_id,)).fetchone()
    if not row:
        return ""
    message_id, raw_message = row
    chunks = []
    size = 0

    def add(values: list[str]) -> bool:
        nonlocal size
        for value in values:
            value = value[:MAX_CONVERSATION_CHARS - size]
            chunks.append(value)
            size += len(value)
            if size >= MAX_CONVERSATION_CHARS:
                return False
        return True

    try:
        if not add(_text(json.loads(raw_message))):
            return "\n".join(chunks)
    except (TypeError, json.JSONDecodeError):
        pass
    for (raw,) in con.execute(
            "select p.data from part p where p.message_id = ?"
            " order by p.time_created, p.id", (message_id,)):
        try:
            if not add(_text(json.loads(raw))):
                break
        except (TypeError, json.JSONDecodeError):
            pass
    return "\n".join(chunks)


def scan_session(con, session_id: str, ignored: dict | None = None, repository_path: str | None = None,
                 scan_prs: bool = True) -> dict:
    initial_text = first_user_message_text(con, session_id)
    tickets = extract_tickets(initial_text)
    prs = extract_prs(initial_text) if scan_prs else []
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


def remove_session(state: Path, session_id: str) -> bool:
    """Drop local associations for an instance removed from OpenDash."""
    data = load(state)
    if session_id not in data:
        return False
    del data[session_id]
    save(state, data)
    return True


def update(state: Path, con, records: list[dict]) -> dict:
    data = load(state)
    changed = False
    for record in records:
        sid = record["session_id"]
        entry = data.setdefault(sid, {})
        repository = os.environ.get("X_BITBUCKET_REPOSITORY")
        directory = str(record.get("directory") or "").rstrip("/").rsplit("/", 1)[-1]
        repository_path = f"{repository.strip('/')}/{directory}" if repository and directory else repository
        if entry.get("initial_scan_complete"):
            found = {"tickets": entry.get("tickets", []),
                     "prs": entry.get("prs", [])}
        else:
            found = scan_session(con, sid, entry.get("ignored"), repository_path)
            # A record can briefly exist before its initial prompt is written.
            # Leave the marker unset so that prompt gets one scan later.
            if first_user_message_text(con, sid).strip():
                entry["initial_scan_complete"] = True
                changed = True
        if entry.get("tickets") != found["tickets"]:
            entry["tickets"] = found["tickets"]
            changed = True
        scanned_prs = {p["number"] for p in found["prs"]}
        existing_prs = [p for p in entry.get("prs", []) if p.get("manual")]
        merged = list(found["prs"])
        for pr in existing_prs:
            if pr["number"] not in scanned_prs:
                merged.append(pr)
        if entry.get("prs") != merged:
            entry["prs"] = merged
            changed = True
    live_ids = {record["session_id"] for record in records}
    for session_id in list(data):
        if session_id not in live_ids:
            del data[session_id]
            changed = True
    if _prune_provider_caches(state, data, records):
        changed = True
    if changed:
        save(state, data)
    return data


def _prune_provider_caches(state: Path, associations: dict,
                           records: list[dict]) -> bool:
    """Drop provider data that is no longer reachable from live instances."""
    tickets = {str(record.get("ticket")).upper() for record in records
               if record.get("ticket")}
    pr_keys: set[str] = set()
    pr_numbers: set[str] = set()
    for entry in associations.values():
        if not isinstance(entry, dict):
            continue
        tickets.update(str(ticket).upper() for ticket in entry.get("tickets", []))
        for candidate in entry.get("prs", []):
            key = _candidate_key(candidate)
            pr_keys.add(key)
            pr_numbers.add(str(candidate.get("number")))

    changed = False
    for filename, allowed, number_fallback in (
            ("jira.json", tickets, False), ("pr.json", pr_keys, True)):
        cache = _cache(state, filename)
        kept = {}
        for key, value in cache.items():
            number = str(value.get("number")) if isinstance(value, dict) else ""
            if key in allowed or (number_fallback and number in pr_numbers):
                kept[key] = value
        if len(kept) != len(cache):
            _write_cache(state, filename, kept)
            changed = True
    return changed


def is_pr_association(association: str) -> bool:
    """True for PR refs (#123, 123) and Bitbucket pull-request URLs.

    Ticket IDs and any other string (including Jira URLs, which contain a
    dash inside the ticket ID) must not be mistaken for PRs.
    """
    return association.lstrip("#").isdigit() or bool(PR_URL_RE.search(association))


def _ticket_from_association(association: str) -> str:
    """Uppercase ticket ID, extracting it from a Jira URL when given one."""
    match = URL_TICKET_RE.search(association)
    return match.group(1).upper() if match else association.upper()


def unlink(state: Path, session_id: str, association: str | None = None,
           kind: str | None = None) -> bool:
    """Remove an association and suppress its rediscovery.

    ``kind`` ("ticket" or "pr") states what the caller selected; without it
    the shape decides: digit refs and Bitbucket PR URLs are PRs, anything
    else is a ticket.
    """
    data = load(state)
    entry = data.setdefault(session_id, {})
    ignored = entry.setdefault("ignored", {"tickets": [], "prs": []})
    ignored.setdefault("tickets", [])
    ignored.setdefault("prs", [])
    changed = False
    is_pr = kind == "pr" or (kind is None and association
                             and is_pr_association(association))
    if not is_pr:
        ticket = _ticket_from_association(association) if association else None
        if ticket and ticket not in ignored["tickets"]:
            ignored["tickets"].append(ticket); changed = True
        if ticket and ticket in entry.get("tickets", []):
            entry["tickets"].remove(ticket); changed = True
        if not ticket:
            for value in entry.get("tickets", []):
                if value not in ignored["tickets"]: ignored["tickets"].append(value); changed = True
            entry["tickets"] = []
    else:
        number = _parse_association(association or "#")
        existing = [p for p in entry.get("prs", []) if str(p.get("number")) != number]
        was_present = len(existing) < len(entry.get("prs", []))
        if was_present:
            entry["prs"] = existing
            if number not in ignored["prs"]:
                ignored["prs"].append(number)
            changed = True
    if changed:
        save(state, data)
    return changed


def clear_associations(state: Path, session_id: str) -> int:
    """Clear and suppress every ticket/PR association for one session."""
    data = load(state)
    entry = data.setdefault(session_id, {})
    ignored = entry.setdefault("ignored", {"tickets": [], "prs": []})
    ignored.setdefault("tickets", [])
    ignored.setdefault("prs", [])
    tickets = entry.get("tickets", [])
    prs = entry.get("prs", [])
    for ticket in tickets:
        if ticket not in ignored["tickets"]:
            ignored["tickets"].append(ticket)
    for pr in prs:
        number = str(pr.get("number"))
        if number not in ignored["prs"]:
            ignored["prs"].append(number)
    entry["tickets"] = []
    entry["prs"] = []
    if tickets or prs:
        save(state, data)
    return len(tickets) + len(prs)


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
    if not is_pr_association(association):
        ticket = _ticket_from_association(association)
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
            pr = {"number": number, "label": label, "manual": True}
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
        raw = response.read(MAX_PROVIDER_BYTES + 1)
        if len(raw) > MAX_PROVIDER_BYTES:
            raise ValueError(f"bridge response exceeds {MAX_PROVIDER_BYTES} bytes")
        value = json.loads(raw or b"{}")
    if not isinstance(value, dict):
        raise ValueError("bridge response must be a JSON object")
    return value


# failure text the agent sometimes fills fields with when a fetch fails;
# a real Jira status name never reads like this
_JUNK_STATUS_RE = re.compile(
    r"unavailable|unknown|\bn/?a\b|error|fail|unable|could not|cannot", re.I)
_JUNK_SUMMARY_RE = re.compile(
    r"^(?:could not|unable to|fetch failed|failed to|no summary|unavailable|"
    r"unknown|n/?a\b|error)", re.I)


def clean_status(status) -> str | None:
    """A status the agent invented to signal a fetch failure is not a status."""
    if not status or _JUNK_STATUS_RE.search(str(status)):
        return None
    return str(status)


def _bounded(value, limit: int = MAX_PROVIDER_TEXT) -> str:
    return str(value or "")[:limit]


def _normalise_ticket(value: dict, ticket: str) -> dict:
    status = value.get("status")
    if isinstance(status, dict):
        status = status.get("name") or status.get("label")
    status = clean_status(status)
    summary = value.get("summary")
    if summary and _JUNK_SUMMARY_RE.match(str(summary)[:40]):
        summary = None
    category = str(value.get("category") or value.get("status_category") or "todo").lower()
    category = {"new": "todo", "to do": "todo", "indeterminate": "progress",
                "in progress": "progress", "done": "done"}.get(category, category)
    return {"fetched": time.time(), "key": ticket, "status": _bounded(status, 200) or None,
            "category": _bounded(category, 100),
            "url": _bounded(value.get("url") or value.get("link")) or None,
            "summary": _bounded(summary) or None, "error": _bounded(value.get("error")) or None}


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


def _normalise_comment(comment: dict) -> dict:
    """Flatten the shapes Bitbucket/the agent may report for one comment."""
    author = comment.get("author") or comment.get("display_name")
    user = comment.get("user")
    if not author and isinstance(user, dict):
        author = user.get("display_name") or user.get("nickname")
    text = comment.get("text")
    if not isinstance(text, str):
        text = comment.get("content")
        if isinstance(text, dict):
            text = text.get("raw") or text.get("html")
    created = (comment.get("created") or comment.get("created_on")
               or comment.get("updated_on") or comment.get("updated"))
    return {"author": _bounded(author, 300), "created": _bounded(created, 100),
            "text": _bounded(text),
            "resolved": bool(comment.get("resolved"))}


def _normalise_checks(value: dict) -> list:
    """Merge checks as {'check', 'passed'} dicts, tolerating plain strings."""
    raw = value.get("merge_checks") or []
    if not isinstance(raw, list):
        return []
    checks = []
    for check in raw[:MAX_PROVIDER_ITEMS]:
        if isinstance(check, dict):
            label = _bounded(check.get("check") or check.get("name"), 500)
            passed = check.get("passed")
            checks.append({"check": label,
                            "passed": passed if isinstance(passed, bool) else None})
        elif str(check):
            checks.append({"check": _bounded(check, 500), "passed": None})
    return checks


def _open_comments(value: dict, pr_author: str) -> list:
    """Comments that are genuinely open feedback.

    Dropped: resolved threads, the PR author's own comments, Clarity review
    summaries ("review completed"), and Security Integration / Change
    Approver bot messages.
    """
    open_comments = []
    comments = value.get("unresolved_comments") or []
    if not isinstance(comments, list):
        return []
    for comment in comments[:MAX_PROVIDER_ITEMS]:
        if not isinstance(comment, dict):
            continue
        norm = _normalise_comment(comment)
        if norm.get("resolved"):
            continue  # the thread was resolved: not open feedback
        author = str(norm.get("author") or "").strip().lower()
        text = str(norm.get("text") or "").lower()
        if pr_author and author == pr_author:
            continue  # the author's own comments are never open feedback
        if "clarity" in author and "review completed" in text:
            continue  # Clarity review summaries, not unresolved comments
        if "security integration" in author or "change approver service account" in author:
            continue  # bot status messages, never open feedback
        open_comments.append(norm)
    return open_comments


def _normalise_pr(value: dict, candidate: dict) -> dict:
    approvals = value.get("approvals")
    builds = value.get("builds") if isinstance(value.get("builds"), dict) else {}
    build_details = value.get("build_details") or []
    if not isinstance(build_details, list):
        build_details = []
    checks = _normalise_checks(value)
    pr_author = str(value.get("author") or "").strip().lower()
    open_comments = _open_comments(value, pr_author)
    threads = int(value.get("unresolved_threads") or 0)
    if open_comments or threads:
        # a thread needs at least one listed comment to be unresolved here
        threads = min(threads, len(open_comments))
    return {
        "fetched": time.time(), "number": str(value.get("number") or candidate.get("number")),
        "label": f"#{value.get('number') or candidate.get('number')}",
        "repository": _bounded(value.get("repository") or candidate.get("repository"), 500),
        "title": _bounded(value.get("title")) or None,
        "url": _bounded(value.get("url") or value.get("link") or candidate.get("url")) or None,
        "status": _normalise_pr_status(value),
        "approvals": approvals if isinstance(approvals, int) else None,
        "needs_update": bool(value.get("needs_update")),
        "unresolved_threads": threads,
        "unresolved_comments": open_comments,
        "merge_checks": checks,
"builds": {"ok": int(builds.get("ok") or 0), "in_progress": int(builds.get("in_progress") or 0),
                    "failed": int(builds.get("failed") or 0),
                    "unavailable": int(builds.get("unavailable") or 0),
                    "error": _bounded(builds.get("error")) or None},
        "build_details": [{"name": _bounded(b.get("name"), 500),
                            "status": _bounded(b.get("status"), 100).upper(),
                            "details": _bounded(b.get("details"))}
                           for b in build_details[:MAX_PROVIDER_ITEMS] if isinstance(b, dict)],
        "tickets": [_bounded(t, 100).upper() for t in value.get("tickets", [])[:MAX_PROVIDER_ITEMS]
                    if isinstance(t, str)],
        "error": _bounded(value.get("error")) or None,
    }


def _cache(state: Path, name: str) -> dict:
    return _read(state / name, {}) or {}


def pr_cache(state: Path) -> dict:
    return _cache(state, "pr.json")


def jira_cache(state: Path) -> dict:
    """Load the ticket cache, with failure placeholders already dropped.

    Entries written before junk rejection carry invented statuses; they must
    never reach the renderer even before the queue refetches them.
    """
    cache = _cache(state, "jira.json")
    for ticket, entry in cache.items():
        if isinstance(entry, dict) and entry.get("status") is not clean_status(entry.get("status")):
            entry["status"] = clean_status(entry.get("status"))
            entry["summary"] = (entry.get("summary")
                                if entry.get("summary") and not _JUNK_SUMMARY_RE.match(
                                    str(entry.get("summary"))[:40]) else None)
    return cache


def failed_gradle_builds(pr_info: list[dict]) -> list[tuple[str, str]]:
    """Return (pr_number, build_name) for FAILED builds whose details mention 'gradle exception'."""
    result = []
    for pr in pr_info:
        if not isinstance(pr, dict):
            continue
        for build in pr.get("build_details") or []:
            if not isinstance(build, dict):
                continue
            status = str(build.get("status") or "").upper()
            details = str(build.get("details") or "").lower()
            if "FAILED" in status and "gradle exception" in details:
                result.append((str(pr.get("number") or ""), str(build.get("name") or "")))
    return result


def _write_cache(state: Path, name: str, value: dict) -> None:
    state.mkdir(parents=True, exist_ok=True)
    path = state / name
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2))
    tmp.replace(path)


def agent_enabled(state: Path) -> bool:
    """Whether background metadata prompts are enabled."""
    return bool(_read(state / AGENT_CONTROL, {"enabled": True}).get("enabled", True))


def set_agent_enabled(state: Path, enabled: bool) -> None:
    _write_cache(state, AGENT_CONTROL, {"enabled": enabled})


def _json_response(text: str) -> dict | None:
    """Extract the first JSON object from an agent response."""
    decoder = json.JSONDecoder()
    text = (text or "")[:MAX_PROVIDER_BYTES]
    for attempt, match in enumerate(re.finditer(r"\{", text)):
        if attempt >= MAX_PROVIDER_ITEMS:
            break
        try:
            value, _ = decoder.raw_decode(text[match.start():])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def _agent_prompt(prs: list[dict], tickets: list[str] | None = None) -> str:
    candidates = json.dumps([
        {key: value for key, value in candidate.items()
         if key in ("number", "repository", "url")}
        for candidate in prs
    ], separators=(",", ":"))
    ticket_ids = json.dumps(sorted({str(t).upper() for t in (tickets or [])}),
                            separators=(",", ":"))
    return (
        "Use the Bitbucket and Jira (Atlassian) MCP tools only. Do not edit files, "
        "run shell commands, or perform any write operation. Fetch the current "
        "pull request title, "
        "status, approval count, whether updates are needed, unresolved review threads "
        "and comments, and build results for these candidates: " + candidates + "\n"
        "Fetch the current status of these Jira tickets with the Jira MCP issue "
        "tool (one call per ticket): " + ticket_ids + "\n"
        "Report each ticket's status name exactly as Jira shows it, together with "
        "its status category (\"To Do\", \"In Progress\" or \"Done\").\n"
        "Omit any ticket or pull request you could not fetch, and never report "
        "failure text, guesses or placeholders such as \"unavailable\", \"unknown\" "
        "or \"fetch failed\" in any field -- the caller preserves cached data "
        "and retries after the normal refresh interval.\n"
        "Verify each comment's thread resolution state in Bitbucket and set its "
        "resolved flag accordingly -- resolved threads must never be listed "
        "or counted. Do not "
        "list or count comments written by the pull request author, Clarity AI "
        "reviewer messages that contain 'review completed' (review summaries, "
        "not open feedback), or messages from the 'Security Integration' and "
        "'Change Approver Service Account' bots. For the repository field "
        "report the pull request's real repository full name as Bitbucket shows it "
        "(for example \"team/repo\"), even when the candidate link only has a UUID "
        "path. "
        "Also read each pull request's merge checks -- the same list the PR overview "
        "page shows (approval requirement, in-progress builds, failed builds, open "
        "tasks and any other blocking requirement) -- reporting each as passed or not. "
        "Return exactly one JSON object and no markdown in this schema: "
        '{"prs":[{"number":"123","repository":"team/project",'
        '"title":"Human readable pull request title",'
        '"author":"Pull request author display name",'
        '"status":"opened","approvals":0,"needs_update":false,'
        '"unresolved_threads":0,"unresolved_comments":'
        '[{"author":"Comment Author","created":"2026-01-01 12:34",'
        '"text":"What the comment says","resolved":false}],'
        '"merge_checks":[{"check":"2+ approvals","passed":true},'
        '{"check":"no in progress builds","passed":false}],'
        '"builds":{"ok":0,"in_progress":0,"failed":0,"unavailable":0},'
        '"build_details":[{"name":"Build Name","status":"SUCCESSFUL","details":"Tests passed: 649"}]}],'
        '"tickets":[{"id":"PCYXC-123","status":"In Product QA",'
        '"category":"In Progress","url":"https://jira/browse/PCYXC-123",'
        '"summary":"Ticket summary"}]}'
    )


def _refresh_via_agent(state: Path, tickets: list[str], prs: list[dict], conf: dict,
                       pull_requests: dict, jira: dict, ttl: float) -> None:
    """Ask a hidden read-only OpenCode session for Bitbucket PR and Jira metadata."""
    if not agent_enabled(state):
        return
    now = time.time()
    prs = [candidate for candidate in prs
           if now - float((pull_requests.get(_candidate_key(candidate)) or
                           pull_requests.get(str(candidate.get("number"))) or {})
                          .get("fetched", 0)) > ttl]
    wanted = {str(t).upper() for t in tickets}
    tickets = sorted(t for t in wanted
                     if now - float(jira.get(t, {}).get("fetched", 0)) > ttl)
    if not prs and not tickets:
        return
    sid = None
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
        ocore.send_prompt(sid, _agent_prompt(prs, tickets), conf["directory"],
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
        if not result or not (isinstance(result.get("prs"), list)
                              or isinstance(result.get("tickets"), list)):
            raise ValueError("metadata agent returned invalid JSON")
        candidates = {_candidate_key(candidate): candidate for candidate in prs}
        by_number = {str(candidate.get("number")): candidate for candidate in prs}
        for value in result.get("prs") or []:
            if not isinstance(value, dict):
                continue
            candidate = candidates.get(_candidate_key(value)) or by_number.get(str(value.get("number")))
            if candidate:
                pull_requests[_candidate_key(candidate)] = _normalise_pr(value, candidate)
        for value in result.get("tickets") or []:
            if not isinstance(value, dict):
                continue
            ticket = str(value.get("id") or value.get("key") or "").upper()
            if ticket in wanted:
                fresh = _normalise_ticket(value, ticket)
                old = jira.get(ticket) or {}
                if not fresh.get("status") and clean_status(old.get("status")):
                    # the fetch failed: keep the last good status, but still
                    # take the turn in the queue instead of wedging it
                    jira[ticket]["fetched"] = fresh["fetched"]
                else:
                    jira[ticket] = fresh
        # Omitted candidates are failed attempts, not candidates that were
        # never tried.  Advance them to the back of the refresh queue while
        # retaining their last good data; otherwise the oldest omission is
        # selected every 30 seconds and grows the hidden agent without bound.
        attempted_at = time.time()
        for candidate in prs:
            key = _candidate_key(candidate)
            entry = (pull_requests.get(key)
                     or pull_requests.get(str(candidate.get("number"))))
            if entry is None:
                entry = dict(candidate)
                pull_requests[key] = entry
            entry["fetched"] = attempted_at
        for ticket in tickets:
            jira.setdefault(ticket, {"key": ticket})["fetched"] = attempted_at
        _write_cache(state, "jira.json", jira)
        _write_cache(state, "pr.json", pull_requests)
        # every cycle is a self-contained prompt/response pair -- the agent
        # needs no memory, so wipe the session's messages entirely and give
        # the next cycle a clean context. Fat JSON pairs would otherwise
        # overflow a 200k window and wedge the session into empty replies.
        ocore.prune_session_messages(sid, keep=0)
    except Exception:
        # A provider outage must never erase the last known PR state.
        # But a session that answers with nothing (context overflow,
        # dead session id after a server restart) would fail forever:
        # drop it so the next cycle starts from a fresh session.
        try:
            if sid:
                ocore.abort_instance(sid)
                ocore.prune_session_messages(sid, keep=0)
        except Exception:
            pass
        try:
            (state / "metadata-agent-session.json").unlink(missing_ok=True)
        except OSError:
            pass
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
            _refresh_via_agent(state, tickets, prs, conf, pull_requests, jira,
                                effective_ttl)
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
                "status", "link", "number", "title", "approvals", "needs_update", "unresolved_threads",
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
