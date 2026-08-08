# Tests

`./test.sh` runs every suite and exits non-zero if any fail. Each suite is a
standalone script that can also be run on its own:

```bash
./test.sh                       # everything
ruby git_review_reply/test.rb   # one suite
zsh  completions/test.zsh
```

| Suite                     | Covers                                              |
| ------------------------- | --------------------------------------------------- |
| `git_review_reply/`       | `zsh/git-review-reply.rb` — `gh` calls are mocked    |
| `completions/test.zsh`    | `zsh/completions.zsh` — the fuzzy TAB behind `v`/`p` |
| `completions/smoke.zsh`   | the same, end to end in a real shell                 |

## How the completion tests work

Two layers. `test.zsh` stubs the completion system and checks what the functions
*ask* zsh to do — fast, exhaustive, where new cases belong. `smoke.zsh` drives a
real interactive shell through a pty and checks what actually lands on the
command line — slow and timing-dependent, so it stays a handful of cases.

### test.zsh — stubbed

`completions.zsh` only talks to zsh's completion system in three places: it
reads the typed word from `$PREFIX`, reports matches with `compadd`, and steers
the UI through `$compstate`. The test stubs all three, so a test is:

```zsh
tab "dow"                  # simulate a fresh TAB on the word "dow"
__p                        # run the real completion function
check "inserts" "Downloads" "${(j: :)ADDED}"
```

`tab` resets `$PREFIX`/`$compstate` (pass `shown` as a second argument to
simulate a *second* consecutive TAB), `ADDED` collects every match handed to
`compadd`, and `GROUPS` records them per call so grouping can be asserted too.

`__v`/`__p` also read `~/Developer` and the cwd, so those tests run against a
throwaway `mktemp -d` tree with `$HOME` and `$PWD` pointed at it. It is removed
on exit.

Covered here:

- `__fuzzy_mark` — where word boundaries land (start, after `-_/.` or a space, camelCase humps)
- `__fuzzy_rank` — the three ranking tiers and their order, empty queries, and that letters mid-word never match
- `__fuzzy_unique` — a lone match across all sections inserts on the first TAB; the same name in two sections still counts as one; two or zero matches leave the word alone
- `__v`/`__p` — cross-section dedup, `__p` offering only directories where `__v` also offers files, and multiple matches still listing as three labelled groups

### smoke.zsh — real pty

Spawns `zsh -f -i` under `zsh/zpty` with the same throwaway `$HOME`, types keys
into it (TABs included) and presses Enter. The sandbox shell defines
`p() { print -r -- "<<$1>>" }`, so whatever TAB left on the command line comes
straight back between `<< >>`. Escape sequences are stripped from the raw pty
output as well, which is how the rendered group headers get asserted.

Covered here: a lone match completing on one TAB, several matches listing
without touching the typed word, the group headers actually rendering, a second
TAB menu-selecting, and `v` offering cwd files where `p` does not.

## Not tested

- **`zstyle` interaction.** The matcher-list configured in `zsh/prompt.zsh` is
  absent from both layers — `test.zsh` bypasses it, `smoke.zsh` starts with `-f`.
- **The `v`/`p` functions themselves** (in `.zshrc`) — only their completions
  are covered, not the `cd`/`nvim` they end up running.
- **Menu cycling past the first entry**, and anything about how a long listing
  paginates.
- **Timing.** `smoke.zsh` waits a fixed 0.4s for zle to settle after each
  keypress. It is stable here, but it is the first thing to suspect on a slow or
  loaded machine; `SETTLE` at the top of the file is the knob.
