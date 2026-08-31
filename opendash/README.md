# opendash

A dashboard for opencode instances working in the background.

Each instance is an opencode session hosted by one shared, detached
`opencode serve` process — so an instance keeps working after you close the
terminal. Run `opendash` again and they are all still there.

```
 opendash  3 instances · 1 working · 1 needs you              server up  14:32:07
 ────────────────────────────────────────────────────────────────────────────────
▌ ◆ PROJ-1204  make the retry backoff configurable            needs you      12s
▌  ◆ bash ./gradlew test --tests RetrySpec
 ▌  payments-PROJ-1204_retry_backoff
  ⠹ PLAT-99  review the search indexer, write REVIEW.md        In Progress     4m
   ▸ Rewriting the tokenizer fast path                    ✓3/7 · +142/-18 · $0.21
   search-indexer
  ● ABC-77  add docstrings to calc.py                                 idle    2h
   · Added docstrings to all 6 functions; no behaviour changes.               ✓2/2
   scratch
```

Line 1 is the ticket, when known, plus what the instance was asked to do — the
title opencode generates for the session, so it sharpens as the agent explores
the work. A Jira status tile appears immediately before the ticket when MCP
metadata is available. Line 2 is what it has actually been doing, and line 3
is the final directory component it works in. The local state comes from opencode's database;
provider metadata comes from the optional MCP bridge.

On the left side of line 3, the final directory component is followed by the
branch icon and name. Worktree rows instead show the main repository path, a
worktree marker, and the worktree branch. The right side shows the same commit
counts as the shell prompt (`↑` ahead, `↓` behind, `+` staged, `~` modified,
`?` untracked), followed by the PR number when one is detected. The `b` action
opens the associated ticket or PR; provider status, approvals, review threads,
and matching build counts remain available through the metadata cache without
making the compact row wrap. The counts include untracked files without
changing the repository index.

Status icons: `⠹` spinner (working), `◆` needs you (blocked on a permission or
a question), `◔` queued, `●` idle, `✖` errored, `○` session gone.

A row also carries the state of its `t` terminal, next to the agent's own,
because an idle agent can easily have a busy terminal:

| | |
|---|---|
| no terminal open | nothing shown |
| running something | `⠸ ❯gradlew t…` — spinner plus the command as typed, trimmed to ten characters |
| finished | `● ❯idle` — the terminal is still open, just at a prompt |

The command comes from the foreground process group on the pane's tty, so a
shell *function* that shells out (your `check`) reports the underlying
`./gradlew`, not `zsh`.

Instances are listed in the order they were started, oldest first, so the list
holds still while you move through it and a new one appears at the bottom
without shifting the rows above it. State never reorders anything — the header
counts what needs you (`1 needs you`) and the `◆` icon marks it in place.

`J` / `K` move the selected instance down / up. The arrangement is kept in the
instance record, so it survives restarts; reordering is disabled while a filter
is active, since the rows you see are not the whole list.

## Running it

```sh
opendash                        # the dashboard (alias is in .zshrc)
```

Nothing to install: `opendash` is a zsh script that runs `dashboard.py` (the
curses UI) or `ocore.py` (server, sessions, db, metadata bridge). Python is
stdlib-only.
Needs `opencode`, `python3` and `tmux` on PATH.

```sh
opendash new "PROJ-1204 make the retry backoff configurable"   # start one here
opendash new -d ~/dev/payments -m anthropic/claude-sonnet-5 "…"
opendash new -w TIX-001-fix-tests "…"   # in a worktree ../<repo>-<branch>
opendash list                   # plain text, no curses
opendash doctor                # check that instances can actually start
opendash abort <session-id>     # interrupt a run
opendash rm <session-id>        # stop it and drop it from the list
opendash unlink <session-id> [ID|#PR]  # unlink and ignore a local association
opendash quit                   # stop every instance and the shared server
opendash server [status|start|stop]
```

`opendash new` picks the ticket out of the task text or a Jira URL, and the
dashboard continues scanning every user and assistant message, so
`PROJ-1204 …` and `https://jira.example.com/browse/PROJ-1204 …` both work.
Pass `-t` to set it explicitly.

Associations are stored separately in `~/.local/state/opendash/metadata.json`.
`opendash unlink ses_... PROJ-1` (or `#123`) removes a local association and
suppresses rediscovery. Omitting the association unlinks detected tickets.

### Neovim

When Neovim is opened in an instance's working directory, `<Space>o` opens a
prompt labelled with that instance's agent name and sends the answer to it,
including the current filename. In visual mode, it also includes the selected
line range and contents. If multiple agents share the directory, Neovim first
opens a selector.
The lualine status displays the same agent state and response preview as the
dashboard, including the working spinner. `<Space>O` keeps the system open-file
action. Neovim uses the `opendash agent` and `opendash prompt` CLI commands, so
the dashboard and editor share the same session.

## Keys

| key | |
|---|---|
| `j` `k` / `↓` `↑` | move the cursor (`g` / `G` for first / last) |
| `J` `K` | move the selected instance down / up the list |
| `z` | minimize or maximize the selected instance |
| `enter`, `o` or `l` | open the instance and talk to it |
| `c` | code actions: `h` runs `check`, `m` runs `gitmm`, `p` commits/pushes, `s` shows `gs`, `r` reviews the branch |
| `t` | terminal in the instance's working directory |
| `n` | new instance — asks for the directory, then opens nvim for the task |
| `f` | follow up: send another message without opening it |
| `a` | abort what the instance is doing right now (asks first) |
| `d` | stop it and remove it from the dashboard (asks first) |
| `u` | unlink and ignore the selected ticket or PR |
| `b` | open the selected ticket or PR in the browser |
| `/` | filter by ticket, title or directory (`esc` clears) |
| `r` / `R` | rename the instance — `r` edits the current name, `R` starts from an empty prompt. The ticket is kept either way, and submitting nothing does nothing |
| `S` `?` | restart the server · keys |
| `q` or `ctrl+c` | leave the dashboard — every instance keeps working |
| `Q` | quit for real: stop all instances and the shared server |

### option+q

`option+q` leaves whatever you opened:

- in an **instance**, it detaches — the agent carries on working;
- in a **`t` terminal**, it closes the terminal if the prompt is idle, and
  only detaches if something is still running, so a long build is never
  killed by accident. "Still running" is decided by `idle-check.sh` from the
  foreground process group on the pane's tty, not from the process name —
  `./gradlew test` makes tmux report the pane as `bash`, and a shell *function*
  that shells out (`check`) reports `zsh`, either of which a name test reads as
  an idle prompt and closes out from under the build. The check closes a session
  only when it positively sees the shell holding the terminal with nothing else
  running; anything it cannot read is treated as busy. Its last decision is
  written to `~/.local/state/opendash/idle-check.last` if you ever need to see
  why it went the way it did.

tmux only reads its config when its **server** starts, so a server left over
from an older opendash would otherwise keep the bindings it started with — which
is how a fixed `option+q` can look unfixed. opendash now sources the current
config onto a running server, so it heals itself; and because the decision lives
in `idle-check.sh`, which is read at each keypress, changing that logic never
needs a restart at all.

A terminal detached while busy then **stays open indefinitely** — it keeps the
shell and its scrollback, and finishing the command does not close it. Press
`t` again to read the output, and `option+q` at the idle prompt to close it for
real. It also goes away with `d` on the instance, with `Q`, or by hand:
`tmux -L opendash kill-session -t sh-<id>`.

`t` always returns to the *same* terminal for a given instance — the tmux
session is named `sh-<id>` after the instance, so pressing it again reattaches
to the one shell, mid-command and all, and never spawns a second. Two
dashboards pressing `t` at once attach as two clients to that same session and
mirror each other.

What does accumulate is one idle shell per instance, roughly 5 MB each, plus
the tmux server at about 4 MB and up to `history-limit` (50 000 lines) of
scrollback per pane — bounded, but worth clearing out if you leave dozens
around. Views whose instance you removed outside the dashboard would linger
unreferenced; to find them:

```sh
comm -13 \
  <(ls ~/.local/state/opendash/instances/*.json | xargs -n1 basename \
      | sed 's/\.json$//' | rev | cut -c1-8 | rev | sort) \
  <(tmux -L opendash ls -F '#{session_name}' | sed 's/^[a-z]*-//' | sort -u)
```

macOS sends `option+q` either as `M-q` or as the literal `œ`, depending on
Ghostty's `macos-option-as-alt`; both are bound, so it works either way and no
Ghostty config change is needed.

### Leaving vs quitting

`q` (or `ctrl+c`) leaves the dashboard and everything keeps running in the
background — close the terminal, come back later, run `opendash` and it is all
still there. `Q` is a real quit: it asks, then stops every instance and the
shared server (`opendash quit` does the same from a script). The conversations
are kept, so reopening still lists the work, idle and ready to continue.

### Starting a task

`n` asks three things: the directory (prefilled with wherever you launched
`opendash`), then a worktree branch, then the request itself in nvim.

Leave the branch blank and the agent works in the directory you gave. Name it
and opendash adds a worktree beside the project — branch `TIX-001-fix-tests`
in `codes` becomes `../codes-TIX-001-fix-tests` — and the agent, its `t`
terminal and the path on the row all point there instead. An existing branch of
that name is checked out rather than refused, so you can pick work back up. The
branch forks from the remote's default branch (`origin/HEAD`, else
`origin/master`, `origin/main`, else `HEAD`), after a best-effort `git fetch`.

The request itself is written in nvim on an empty buffer, so it can be as long
as you like. Save to start the instance; `:cq` or
saving nothing cancels. The buffer is a scratch file named after the target
directory, so nvim's statusline tells you where the work will happen.

The editor is `nvim` if it is on PATH, else `$EDITOR`; override with
`OPENDASH_EDITOR`. Follow-ups (`f`) stay on a quick single-line prompt — for
anything longer, open the instance and use opencode's own composer.

## MCP metadata

OpenDash never calls Jira or Bitbucket REST. It optionally sends candidate
tickets and pull requests to a remote OpenCode HTTP bridge, which owns the MCP
connection and uses a dedicated read-only metadata session. The active agent
session is never used and no metadata prompts are added to it. Without a
bridge, detection and the dashboard continue to work with cached or local
associations only.

Set `OPENDASH_MCP_URL` (or `mcp_url` in `config.json`):

```json
{
  "mcp_url": "https://metadata-host.example/opendash/metadata",
  "mcp_tool": "opendash_metadata",
  "mcp_agent": "metadata-readonly",
  "mcp_directory": "~/.local/share/opendash-metadata",
  "metadata_refresh": 45,
  "model": "anthropic/claude-sonnet-5",
  "agent": "build"
}
```

The bridge receives a POST document containing `contract: "opendash-mcp-v1"`,
`read_only: true`, a reusable session descriptor, and candidate `tickets` and
`prs`. It must return JSON with `tickets` keyed by ID and `prs` either in
request order or keyed by `repository#number`. PR results may contain
`status` (`opened`, `rejected`, `needs changes`, `approved`, or `merged`), `url`,
`number`, `approvals`, `needs_update`, `unresolved_threads`,
`unresolved_comments`, `tickets`, and `builds` (`ok`, `failed`, `unavailable`,
optional `error`). The
bridge must count unresolved threads only when the last comment author is not
the PR opener, and classify ambiguous builds against the project changed by
the PR before counting them. Missing fields remain unknown, never fabricated.
It may return `{"session":{"id":"..."}}` to establish or rotate the
persisted dedicated session.

Results are cached in `jira.json` and `pr.json`; the default refresh interval
is 45 seconds and can be changed with `OPENDASH_METADATA_REFRESH`. Only stale
candidate IDs are requested. A timeout, malformed response, or unavailable
endpoint leaves old values in place and does not block the dashboard.

## Configuration

Environment overrides everything in `config.json`.

| | |
|---|---|
| `OPENDASH_MODEL` / `model` | default `provider/model` for new instances |
| `OPENDASH_AGENT` / `agent` | opencode agent (default `myagent`, set in `config.json`) |
| `OPENDASH_MCP_URL` | remote read-only MCP metadata bridge |
| `OPENDASH_MCP_TOOL` / `OPENDASH_MCP_AGENT` | bridge tool and dedicated agent names |
| `OPENDASH_MCP_DIRECTORY` | isolated bridge session directory |
| `OPENDASH_MCP_TIMEOUT` | bridge request timeout, default 8 seconds |
| `OPENDASH_METADATA_REFRESH` | metadata cache TTL, default 45 seconds |
| `OPENDASH_EDITOR` | editor for writing tasks (default `nvim`, else `$EDITOR`) |
| `OPENDASH_PERMISSION` | JSON object of tool permissions for instances |
| `OPENDASH_AUTO=0` | make instances read-only instead of unattended |
| `OPENDASH_CONFIG` | alternative config.json path |
| `OPENDASH_STATE` | state dir (default `~/.local/state/opendash`) |
| `OPENDASH_TMUX_SOCKET` | tmux socket name (default `opendash`) |
| `OPENDASH_PYTHON` | python to run (default `python3`) |

## How it works

- **One shared server.** `opencode serve` on a random port, started detached
  and recorded in `~/.local/state/opendash/server.json`. Instances run *in*
  it, which is why they survive the shell closing.
- **Instances** are opencode sessions; `~/.local/state/opendash/instances/`
  holds only what opencode does not know (the ticket, the original task).
- **Live state** is read from `~/.local/share/opencode/opencode.db` read-only
  (title, todos, tokens, cost) plus `GET /permission` for anything blocked
  waiting on you.
- **Metadata** scans every user and assistant message/part for ticket IDs and
  PR URLs/references. Provider facts are fetched only by the optional remote
  MCP bridge in a background worker and cached on disk.
- **Opening** an instance runs `opencode attach` in a private tmux server
  (socket `opendash`), which is what makes `option+q` interceptable and keeps
  your scroll position between visits.
- **Instances run as `opencode --auto --agent myagent` would.** There is no
  per-instance `opencode` process to pass flags to, so the two halves are set
  where they actually live: `--auto` becomes `OPENCODE_PERMISSION` on the
  shared server (tools allowed up front, since nobody is watching to approve
  them), and `--agent` is sent with the opening prompt, which is what puts the
  session on `myagent`. Both are defaults you can change — `OPENDASH_AUTO=0`
  for read-only instances, `OPENDASH_PERMISSION` for something in between, and
  `agent` in `config.json` or `--agent` per instance. `question` is always left
  asking, and the dashboard surfaces it as **needs you**.

## What `d` actually removes

Removing an instance stops its work and forgets it, but does not delete the
conversation and does not kill any long-lived process:

| | |
|---|---|
| the running turn | **aborted** — the message ends in `MessageAbortedError` |
| tool subprocesses | die with the aborted turn |
| the `oc-`/`sh-` tmux views | killed |
| the instance record | deleted from `instances/` |
| the opencode session | **kept** — still in `opencode session list` |
| the worktree | removed |
| **its branch** | **kept, untouched** — check it out again whenever |
| the shared `opencode serve` | **untouched** — it hosts your other instances |

Uncommitted changes in the worktree stop the removal and say so; answering the
second prompt discards them (`opendash rm -f` from a script). The branch is
never touched either way, so committed work is always still there.

There is no per-instance process to kill: every instance lives inside the one
shared server. To check by hand:

```sh
pgrep -fl "opencode serve"                     # the shared server, still there
pgrep -P "$(jq -r .pid ~/.local/state/opendash/server.json)"   # live tool children
tmux -L opendash ls                            # views; the removed one is gone
cd <the instance's dir> && opencode session list   # conversation still listed
```

`opencode session list` is directory-scoped, so run it from the directory the
instance was working in. To see how a run ended:

```sh
sqlite3 -readonly ~/.local/share/opencode/opencode.db "
  select json_extract(data,'\$.error.name'),
         json_extract(data,'\$.time.completed') is not null as finished
  from message where session_id='ses_…' and json_extract(data,'\$.role')='assistant'"
```

## Stopping the server

`opendash server stop` (and `Q`) end the process that hosts the agents. What
survives is everything on disk: the instance records, and every conversation,
todo list and cost in opencode's own database. Reopening the dashboard restarts
the server and lists them all again, ready to continue with `f` or by opening
them.

What does not survive is a run that was **in flight** — that agent was mid-turn
in the process you killed. Those show as `interrupted when the server stopped —
send a follow-up to carry on` rather than spinning forever, because a run
belongs to the process that started it: an unfinished message older than the
current server cannot still be running.

Worktrees, branches and `t` terminals are untouched by a server restart.

## An instance that never starts

opencode reads its config when the **server** starts, so an agent defined
afterwards is unknown to a server that is already running. Prompting with it
gets an HTTP 204 and then dies server-side, which showed up as an instance
sitting in `queued — waiting for the model` forever while a message typed into
the agent itself worked fine — the TUI sends whichever agent it has selected.

opendash now checks the agent against the running server before creating
anything and says so:

```
the running opencode server does not know agent 'myagent' (it knows: build,
compaction, …). It was probably started before the agent was defined --
restart it with S in the dashboard or `opendash server stop`.
```

An instance that produces nothing at all within 25 seconds is also reported as
an error rather than staying queued, and the row shows the server's own reason,
read out of `opencode.log` — `prompt_async` answers 204 and can still die
afterwards, so its log is the only place the cause exists.

`opendash doctor` checks the whole chain in the order an instance needs it —
binaries, server, the agents it knows, the configured agent and model, the
database — and then actually sends a test prompt and waits for a reply:

```
  ok   server agents          build, compaction, …, myagent
  ok   configured agent       myagent
  ok   test run started       the agent replied
```

Run it on a machine where instances will not start; it names the broken link.

## When something gets stuck

Everything routine goes through `opendash`, but two independent layers sit
underneath and you can drive either by hand.

**The views live in a private tmux server** (socket `opendash`), one session per
thing you opened: `oc-<id>` for an instance's TUI, `sh-<id>` for a `t` terminal.

```sh
tmux -L opendash ls                          # what is open
tmux -L opendash attach -t oc-1a2b3c4d       # attach without the dashboard
tmux -L opendash kill-session -t sh-1a2b3c4d
tmux -L opendash kill-server                 # close every view
```

Killing a view never stops an agent — the agent runs in the shared server and
tmux only holds the screen; the next `enter` builds a fresh view. (Do pass
`-L opendash`, or you will be talking to your own tmux server.)

**The agents live in the detached `opencode serve` process**, so tmux cannot
reach them:

```sh
opendash abort <session-id>          # interrupt one run
opendash server status|stop|start    # restarting drops in-flight runs
opendash quit                        # stop everything
```

State is plain files, safe to read or delete:
`~/.local/state/opendash/{server.json,server.log,instances/*.json}`. Server
startup problems land in `server.log`; opencode's own log is
`~/.local/share/opencode/log/opencode.log`.

Instances are ordinary opencode sessions, so opencode's CLI still sees them —
`opencode session list`, `opencode --session <id>` — and deleting
`~/.local/state/opendash/` only loses the ticket/task notes, not the work.

## Tests

```sh
./tests/run            # everything, lower levels first
./tests/run --fast     # skip the levels that drive tmux and the ui
./tests/run test_db    # one module, or one case: test_db.States
```

Stdlib `unittest`, nothing to install. Each level builds its own world under a
temp directory — its own state dir, its own stand-in opencode database, its own
tmux socket — so a run never touches your real instances.

| | |
|---|---|
| `test_unit` | pure functions: tickets, headlines, ordering, permissions, clipping |
| `test_mocked` | the http layer stubbed out: failed prompts, server ownership |
| `test_db` | `snapshot()` against a stand-in database: every state, todos, activity, reordering, renaming |
| `test_git` | worktrees against a real repository: naming, branch reuse, removal keeping the branch, dirty refusal |
| `test_tmux` | real panes: what `option+q` decides, and what a `t` terminal reports |
| `test_tui` | the dashboard in a terminal, driven by keystrokes and asserted against the screen |

`OPENDASH_NO_SERVER=1` opens the dashboard without starting or contacting a
server, which is how the ui level runs on its own.

Three real bugs came out of writing these: a zombie process counted as a
running job (so an idle terminal looked busy and `option+q` would not close
it), `esc` taking a second to clear the filter because of ncurses' `ESCDELAY`,
and the dashboard refusing to open at all when the server could not start.

## Design notes

Things that were tried and rejected, so they do not get retried:

- **`esc` to leave an instance, only in "normal mode".** opencode's prompt
  reports a `block` cursor the whole time it is idle (checked with
  `tmux display -p '#{cursor_shape}'`), so there is no mode for tmux to detect,
  and grabbing `esc` would steal the key opencode uses to interrupt a run.
  Hence a dedicated `option+q`. Modal state *is* detectable while an external
  `$EDITOR` is open (`#{pane_current_command}` is `nvim`, cursor `block` vs
  `bar`) — that window is just too narrow to be useful.
- **`ctrl+w` as the leave key** — opencode already uses it for
  delete-word-back. Of the plain ctrl keys only `q`, `s`, `o`, `h` and `y` are
  unused by opencode.
- **Driving instances through `opencode --session … --prompt …` in tmux.**
  `--prompt` does not submit when resuming a session, and it would tie the
  agent's life to the tmux pane. Posting to `/session/{id}/prompt_async` on the
  shared server instead is what makes the work outlive the terminal.
- **`GET /session/status` and `/api/session/{id}/permission`** both come back
  empty for another process's sessions. Run state comes from the db (last
  assistant message without `time.completed`), and blocked runs from
  `GET /permission?directory=…`, which is directory-scoped.
- **A bare `OPENCODE_PERMISSION="allow"`.** opencode merges that value into an
  object, so a string is spread into characters and every opencode client then
  fails config validation. It has to be a JSON object.
