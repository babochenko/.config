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
▌  ~/dev/payments-PROJ-1204_retry_backoff
  ⠹ PLAT-99  review the search indexer, write REVIEW.md        In Progress     4m
   ▸ Rewriting the tokenizer fast path                    ✓3/7 · +142/-18 · $0.21
   ~/dev/search-indexer
  ● ABC-77  add docstrings to calc.py                                 idle    2h
   · Added docstrings to all 6 functions; no behaviour changes.               ✓2/2
   ~/dev/scratch
```

Line 1 is the ticket plus what the instance was asked to do — the title
opencode generates for the session, so it sharpens as the agent explores the
work. Line 2 is what it has actually been doing, and line 3 is the directory it
works in. All of it comes from opencode's own database, not from guessing.

Status icons: `⠹` spinner (working), `◆` needs you (blocked on a permission or
a question), `◔` queued, `●` idle, `✖` errored, `○` session gone.

Instances are listed in the order they were started, oldest first, so the list
holds still while you move through it and a new one appears at the bottom
without shifting the rows above it. State never reorders anything — the header
counts what needs you (`1 needs you`) and the `◆` icon marks it in place.

## Running it

```sh
opendash                        # the dashboard (alias is in .zshrc)
```

Nothing to install: `opendash` is a zsh script that runs `dashboard.py` (the
curses UI) or `ocore.py` (server, sessions, db, jira). Python is stdlib-only.
Needs `opencode`, `python3` and `tmux` on PATH.

```sh
opendash new "PROJ-1204 make the retry backoff configurable"   # start one here
opendash new -d ~/dev/payments -m anthropic/claude-sonnet-5 "…"
opendash list                   # plain text, no curses
opendash abort <session-id>     # interrupt a run
opendash rm <session-id>        # stop it and drop it from the list
opendash quit                   # stop every instance and the shared server
opendash server [status|start|stop]
```

`opendash new` picks the ticket out of the task text or a Jira URL, so
`PROJ-1204 …` and `https://jira.example.com/browse/PROJ-1204 …` both work.
Pass `-t` to set it explicitly.

## Keys

| key | |
|---|---|
| `j` `k` / `↓` `↑` | move (`g` / `G` for first / last) |
| `enter` or `l` | open the instance and talk to it |
| `t` | terminal in the instance's working directory |
| `n` | new instance — asks for the directory, then opens nvim for the task |
| `f` | follow up: send another message without opening it |
| `a` | abort what the instance is doing right now (asks first) |
| `d` | stop it and remove it from the dashboard (asks first) |
| `/` | filter by ticket, title or directory (`esc` clears) |
| `r` | rename the instance — the ticket is kept |
| `R` `S` `?` | refresh · restart the server · keys |
| `q` or `ctrl+c` | leave the dashboard — every instance keeps working |
| `Q` | quit for real: stop all instances and the shared server |

### option+q

`option+q` leaves whatever you opened:

- in an **instance**, it detaches — the agent carries on working;
- in a **`t` terminal**, it closes the terminal if the prompt is idle, and
  only detaches if something is still running, so a long build is never
  killed by accident.

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

`n` asks for the directory first — prefilled with wherever you launched
`opendash`, editable — and then opens nvim on an empty buffer for the request
itself, so it can be as long as you like. Save to start the instance; `:cq` or
saving nothing cancels. The buffer is a scratch file named after the target
directory, so nvim's statusline tells you where the work will happen.

The editor is `nvim` if it is on PATH, else `$EDITOR`; override with
`OPENDASH_EDITOR`. Follow-ups (`f`) stay on a quick single-line prompt — for
anything longer, open the instance and use opencode's own composer.

## Jira status

With credentials, the ticket's real status is polled every few minutes and
coloured by category (grey to-do, yellow in progress, green done). Without
them the ticket id is still shown, with the instance's own state next to it.

Set `JIRA_BASE_URL`, `JIRA_EMAIL` and `JIRA_API_TOKEN`, or put them in
`~/.config/opendash/config.json`:

```json
{
  "jira_base_url": "https://your-org.atlassian.net",
  "jira_email": "you@your-org.com",
  "model": "anthropic/claude-sonnet-5",
  "agent": "build"
}
```

The token is also read from the macOS keychain if you keep it there:

```sh
security add-generic-password -s jira-api-token -a "$USER" -w
```

Untested against a live Jira — there were no credentials on this machine when
it was written. If the status pill stays blank, look at
`~/.local/state/opendash/jira.json`: each ticket caches either a `status` and
`category`, or the `error` that came back.

## Configuration

Environment overrides everything in `config.json`.

| | |
|---|---|
| `OPENDASH_MODEL` / `model` | default `provider/model` for new instances |
| `OPENDASH_AGENT` / `agent` | opencode agent (default `myagent`, set in `config.json`) |
| `JIRA_BASE_URL` `JIRA_EMAIL` `JIRA_API_TOKEN` | jira polling |
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
| the shared `opencode serve` | **untouched** — it hosts your other instances |

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
