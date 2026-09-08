"""Pure presentation helpers for pull requests.

Everything here is curses-free: given normalised PR dictionaries (see
metadata._normalise_pr) these build row labels, colors, grouping and the
overlay lines. The dashboard imports them; tests exercise them directly.
"""
from __future__ import annotations

import contextlib
import time
import unicodedata

import metadata
import ocore

C_WORK, C_OK, C_ERR, C_ATT, C_DIM, C_TICKET, C_ACCENT, C_SEL = range(1, 9)


SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


# ------------------------------------------------------------------ text utils

def _w(ch: str) -> int:
    if ch in ("\ufe0e", "\ufe0f"):
        return 0            # variation selectors are zero-width
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def _tw(text: str) -> int:
    """Total display width of a string."""
    return sum(_w(c) for c in text)


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



_PR_STATUS_ICON = {
    "merged": "✓",
    "open": "◐",
    "declined": "✖",
    "superseded": "→",
}


def _pr_label(pr: dict, loading: bool = False, frame: int = 0) -> str:
    """Format the compact PR status shown on the location line."""
    status = str(pr.get("status") or "").lower()
    prefix = _PR_STATUS_ICON.get(status, "")
    label = prefix + "#" + str(pr.get("number") or "")

    if status == "merged":
        return label

    has_stats = (pr.get("approvals") is not None
                 or pr.get("unresolved_threads")
                 or (pr.get("builds") or {}).get("ok")
                 or (pr.get("builds") or {}).get("failed"))
    if loading and not has_stats:
        label += " " + SPINNER[frame % len(SPINNER)]
    if pr.get("approvals"):
        label += f" ✓{pr['approvals']}"
    if pr.get("needs_update"):
        label += " !"
    if pr.get("unresolved_threads"):
        label += f" ⊟{pr['unresolved_threads']}"
    builds = pr.get("builds") or {}
    if any(builds.get(k) for k in ("ok", "in_progress", "failed", "unavailable")):
        if builds.get("ok") and not any(builds.get(k) for k in
                                        ("in_progress", "failed", "unavailable")):
            label += " ⚙"  # every build green: the count is noise
        else:
            parts = []
            if builds.get("ok"):
                parts.append(f"{builds['ok']}✓")
            if builds.get("in_progress"):
                parts.append(f"{builds['in_progress']}◔")
            if builds.get("failed"):
                parts.append(f"{builds['failed']}✗")
            label += " ⚙" + "/".join(parts)
            if builds.get("unavailable"):
                label += f"/{builds['unavailable']}?"
    return label


_STALE_AFTER: float | None = None


def _stale_after() -> float:
    """Age (seconds) beyond which cached PR metadata counts as stale: twice the refresh period."""
    global _STALE_AFTER
    if _STALE_AFTER is None:
        _STALE_AFTER = 2.0 * metadata.DEFAULT_REFRESH
        with contextlib.suppress(Exception):
            _STALE_AFTER = 2.0 * float(metadata.mcp_config()["refresh"])
    return _STALE_AFTER


def _pr_stale_age(prs: list) -> str | None:
    """Age of the oldest successful PR fetch, if it exceeds twice the refresh period.

    Failed fetches (entries with an error) do not count as successful: their
    `fetched` keeps moving forward, so they are skipped and the badge tracks
    the last time real data landed.
    """
    worst = 0.0
    for pr in prs:
        if pr.get("error"):
            continue
        fetched = pr.get("fetched")
        try:
            worst = max(worst, time.time() - float(fetched))
        except (TypeError, ValueError):
            pass
    if worst <= _stale_after():
        return None
    return ocore.fmt_age(int((time.time() - worst) * 1000))


def _pr_row_pair(pr: dict) -> int:
    """Colour for a PR's row label: merged -> green, ready for review -> yellow, other -> blue.

    "Ready for review" means every merge check passes except the required
    approvals one: the only failing check, if any, must be an approval check.
    """
    if str(pr.get("status") or "").lower() == "merged":
        return C_OK
    checks = pr.get("merge_checks") or []
    fails = [str(c.get("check") or "").lower() for c in checks if c.get("passed") is False]
    if checks and (not fails or (len(fails) == 1 and "approval" in fails[0])):
        return C_WORK
    return C_TICKET


# display order for PRs: in progress (blue) -> ready for review (yellow) -> merged (green)
_PR_RANK = {C_TICKET: 0, C_WORK: 1, C_OK: 2}


def _pr_rank(pr: dict) -> tuple:
    try:
        number = int(str(pr.get("number") or 0))
    except ValueError:
        number = 0
    return (_PR_RANK.get(_pr_row_pair(pr), 3), number)


def _grouped_pr_labels(prs: list, loading: bool = False, frame: int = 0) -> list[list[tuple[str, int]]]:
    """Group PRs by repository name: parrot#123 infra-apps-conf(#1001 #1002).

    PRs sort by state first (in progress, ready for review, merged), so both
    the groups and the PRs inside a group follow that order. Each group is a
    list of (text, colour) segments: the repository name and parentheses in
    white, every PR and its stats in its own state colour.
    """
    by_repo: dict[str, list] = {}
    order: list[str] = []
    for pr in sorted(prs, key=_pr_rank):
        repo = pr.get("repository") or ""
        name = repo.rsplit("/", 1)[-1] if repo else ""
        if name not in by_repo:
            by_repo[name] = []
            order.append(name)
        by_repo[name].append(pr)
    groups = []
    for name in order:
        group = by_repo[name]
        if len(name) > 16:
            name = clip(name, 16)  # uuid-style repo names must not eat the row
        pr_labels = [(_pr_label(pr, loading, frame), _pr_row_pair(pr)) for pr in group]
        if len(group) == 1:
            segments = ([(name, C_SEL), pr_labels[0]] if name else [pr_labels[0]])
        else:
            segments = [(f"{name}(", C_SEL)]
            for n, (text, pair) in enumerate(pr_labels):
                if n:
                    segments.append((" ", C_SEL))
                segments.append((text, pair))
            segments.append((")", C_SEL))
        groups.append(segments)
    return groups



def _pr_overlay_segments(pr: dict) -> list[list[tuple[str, int, bool, str | None]]]:
    """Build displayable lines (segments of (text, color pair, bold, url)) for one PR."""
    status = str(pr.get("status") or "").lower()
    pair = {"merged": C_OK, "approved": C_OK, "open": C_TICKET, "opened": C_TICKET,
            "draft": C_WORK, "rejected": C_ERR, "declined": C_ERR,
            "superseded": C_ERR, "needs changes": C_ERR}.get(status, C_DIM)
    url = pr.get("url") or ""
    comments = pr.get("unresolved_comments") or []
    lines: list[list[tuple[str, int, bool, str | None]]] = [
        [("  ", C_DIM, False, None),
         (f"#{pr.get('number')} ", C_SEL, True, None),
         (status or "unknown", pair, False, None),
         (f"  {pr.get('title') or ''}", C_SEL, True, None)],
        [("  ", C_DIM, False, None),
         (url, C_TICKET, False, url or None)],
    ]
    # a merged PR is done -- no stats, checks, builds or comments to review
    if status == "merged":
        return lines
    repo = pr.get("repository") or ""
    if repo:
        lines.append([(f"  repo: {repo}", C_DIM, False, None)])

    stats: list[tuple[str, int]] = []
    if pr.get("approvals") is not None:
        stats.append((f"approvals: {pr.get('approvals')}",
                      C_OK if pr.get("approvals") else C_DIM))
    if pr.get("needs_update"):
        stats.append(("needs update", C_ERR))
    if pr.get("unresolved_threads"):
        stats.append((f"unresolved threads: {pr['unresolved_threads']}", C_DIM))
    if comments:
        stats.append((f"open comments: {len(comments)}", C_DIM))
    builds = pr.get("builds") or {}
    if any(builds.get(k) for k in ("ok", "in_progress", "failed", "unavailable")):
        parts: list[tuple[str, int]] = []
        if builds.get("ok"):
            parts.append((f"{builds['ok']}✓", C_OK))
        if builds.get("in_progress"):
            parts.append((f"{builds['in_progress']}◔", C_WORK))
        if builds.get("failed"):
            parts.append((f"{builds['failed']}✗", C_ERR))
        if builds.get("unavailable"):
            parts.append((f"{builds['unavailable']}?", C_DIM))
        stats.append(("builds: " + "/".join(text for text, _ in parts),
                      parts[-1][1]))
    if stats:
        segs: list[tuple[str, int, bool, str | None]] = [("  ", C_DIM, False, None)]
        for n, (text, colour) in enumerate(stats):
            if n:
                segs.append(("  ", C_DIM, False, None))
            segs.append((text, colour, False, None))
        lines.append(segs)

    checks_passed = [str(c.get("check") or "") for c in pr.get("merge_checks") or []
                     if c.get("passed") is True]
    checks_failed = [str(c.get("check") or "") for c in pr.get("merge_checks") or []
                      if c.get("passed") is False]
    for check in pr.get("merge_checks") or []:
        label = str(check.get("check") or "")
        if not label or check.get("passed") is not None:
            continue
        lines.append([(f"    · {label}", C_DIM, False, None)])
    if checks_failed:
        lines.append([(f"    ✗ {len(checks_failed)} check{'s' if len(checks_failed) != 1 else ''} failed — ",
                       C_ERR, False, None),
                      (", ".join(checks_failed), C_ERR, False, None)])
    if checks_passed:
        lines.append([(f"    ✓ {len(checks_passed)} check{'s' if len(checks_passed) != 1 else ''} passed — ", C_OK, False, None),
                      (", ".join(checks_passed), C_OK, False, None)])

    tickets = pr.get("tickets") or []
    if tickets:
        lines.append([("  tickets: ", C_DIM, False, None),
                      (", ".join(tickets), C_TICKET, False, None)])
    passed, queued, failed = [], [], []
    for build in pr.get("build_details") or []:
        bstatus = str(build.get("status") or "").upper()
        if "FAIL" in bstatus:
            failed.append((build, bstatus))
        elif "SUCCESS" in bstatus:
            passed.append((build, bstatus))
        else:
            queued.append((build, bstatus))
    for build, bstatus in failed:
        lines.append([(f"    ✗ {build.get('name') or '?'}", C_ERR, True, None),
                      (f" — {bstatus}", C_ERR, True, None)])
        if build.get("details"):
            lines.append([(f"      {build['details']}", C_DIM, False, None)])
    if queued:
        names = ", ".join((b.get("name") or "?").rsplit("/", 1)[-1].strip()
                          for b, _ in queued)
        lines.append([(f"    ◔ {len(queued)} build{'s' if len(queued) != 1 else ''} in progress — ", C_WORK, False, None),
                      (names, C_WORK, False, None)])
    if passed:
        names = ", ".join((b.get("name") or "?").rsplit("/", 1)[-1].strip()
                          for b, _ in passed)
        lines.append([(f"    ✓ {len(passed)} build{'s' if len(passed) != 1 else ''} passed — ", C_OK, False, None),
                      (names, C_OK, False, None)])
    for comment in comments:
        author = comment.get("author") or ""
        text = comment.get("text") or ""
        created = str(comment.get("created") or "")[:16].replace("T", " ").rstrip()
        if not author and not text:
            continue  # count is already in the stats line
        prefix = f"    ⊟ {author}".rstrip()
        if created:
            prefix += f" {created}"
        lines.append([(prefix + ": ", C_DIM, False, None),
                      (clip(text, 120), C_DIM, False, None)])
    return lines
