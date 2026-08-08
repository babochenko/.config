#!/usr/bin/env zsh
# End-to-end smoke tests for the `v`/`p` completion, driven through a real pty.
#
# Where test.zsh stubs the completion system and asserts on what the functions
# *asked* zsh to do, this drives an actual interactive zsh over zsh/zpty: it
# types "p ev<TAB>", presses Enter, and looks at what the shell really ran.
# Slower and inherently timing-dependent, so it stays a handful of smoke tests —
# test.zsh remains the place to cover behaviour in detail.
#
# The trick for observing the line buffer: the sandbox shell defines
# `p() { print -r -- "<<$1>>" }`, so whatever TAB left on the command line comes
# back to us between << >> once Enter runs it.
#
# Run: zsh zsh/tests/completions/smoke.zsh   (or via zsh/tests/test.sh)

emulate -L zsh
setopt extended_glob

if ! zmodload zsh/zpty 2>/dev/null; then
  print -r -- "SKIP: zsh/zpty module unavailable"
  exit 0
fi
zmodload zsh/datetime

typeset -g PASSED=0 FAILED=0
typeset -gF SETTLE=0.4   # seconds to let zle finish a keypress before the next

# --------------------------------------------------------------- sandbox ----

typeset -g SANDBOX="$(mktemp -d)"
cleanup() { zpty -d sh 2>/dev/null; rm -rf "$SANDBOX" }
trap cleanup EXIT INT TERM

mkdir -p "$SANDBOX"/Developer/{eventstore,my-docs} "$SANDBOX"/work/{nvim,notes}
touch "$SANDBOX"/work/readme.md

# ------------------------------------------------------------- pty driver ---

# Accumulate pty output until <pattern> shows up; leaves it all in $REPLY.
await() {
  local pat="$1" chunk="" out=""
  local -F deadline=$(( EPOCHREALTIME + ${2:-5} ))
  while (( EPOCHREALTIME < deadline )); do
    if zpty -rt sh chunk 2>/dev/null; then
      out+="$chunk"
      [[ "$out" == *${~pat}* ]] && { REPLY="$out"; return 0 }
    else
      sleep 0.02
    fi
  done
  REPLY="$out"; return 1
}

# env -i keeps the login environment out; PATH is still needed for `ls`.
zpty sh env -i HOME="$SANDBOX" TERM=xterm PATH="$PATH" zsh -f -i

for line in \
  'PS1=""; PS2=""; RPS1=""; unsetopt beep' \
  'autoload -Uz compinit && compinit -u -d $HOME/.zcompdump' \
  "source ${0:A:h}/../../completions.zsh" \
  'p() { print -r -- "<<$1>>" }' \
  'v() { print -r -- "<<$1>>" }' \
  "cd $SANDBOX/work"
do zpty -w sh "$line"; done

zpty -w sh 'print SETUP_OK'
if ! await 'SETUP_OK'; then
  print -r -- "FAILED: sandbox shell never came up: ${(V)REPLY}"
  exit 1
fi

# Type <keys> (TABs and all), press Enter, and return what the shell received.
# Sets: WORD, the completed word; SCREEN, the raw pty output with the escape
# sequences and carriage returns stripped, for asserting on the listing.
typeset -g WORD SCREEN
type_keys() {
  local keys="$1" out
  zpty -w -n sh "$keys"; sleep $SETTLE   # let zle complete before Enter lands
  zpty -w -n sh $'\n'
  await '>>' 5
  out="$REPLY"
  SCREEN="${${out//$'\e'\[[0-9;?]#[a-zA-Z]/}//[$'\r'$'\b']/}"
  if [[ "$out" == *'<<'(#b)([^\>]#)'>>'* ]]; then WORD="$match[1]"; else WORD="<no output>"; fi
}

# ---------------------------------------------------------------- asserts ---

suite() { print; print -r -- "$1" }

check() {  # check <what> <expected> <actual>
  if [[ "$2" == "$3" ]]; then
    (( PASSED++ )); print -r -- "  ok   $1"
  else
    (( FAILED++ ))
    print -r -- "  FAIL $1"
    print -r -- "         expected: ${(V)2}"
    print -r -- "         actual:   ${(V)3}"
  fi
}

contains() {  # contains <what> <needle> <haystack>
  if [[ "$3" == *"$2"* ]]; then
    (( PASSED++ )); print -r -- "  ok   $1"
  else
    (( FAILED++ ))
    print -r -- "  FAIL $1"
    print -r -- "         missing: ${(V)2}"
    print -r -- "         screen:  ${(V)3}"
  fi
}

# ------------------------------------------------------------------ tests ---

suite "one TAB, one match: completes on the spot"

type_keys $'p ev\t'
check "~/Developer project"        "eventstore"  "$WORD"

type_keys $'p no\t'
check "directory in the cwd"       "notes"       "$WORD"

type_keys $'p nv\t'
check "shortcut and cwd, one name" "nvim"        "$WORD"

suite "one TAB, several matches: lists, leaves the word alone"

type_keys $'p d\t'
check "typed word survives"        "d"                    "$WORD"
contains "shortcuts group shown"   "=== shortcuts ==="    "$SCREEN"
contains "  with its matches"      "Developer  Downloads" "$SCREEN"
contains "~/Developer group shown" "=== ~/Developer ==="  "$SCREEN"
contains "  with its matches"      "my-docs"              "$SCREEN"

suite "second TAB: menu-selects the first match"

type_keys $'p d\t\t'
check "first match inserted"       "Developer"   "$WORD"

suite "v and p offer different things"

type_keys $'v re\t'
check "v completes a cwd file"     "readme.md"   "$WORD"

type_keys $'p re\t'
check "p ignores cwd files"        "re"          "$WORD"

# ---------------------------------------------------------------- results ---

print
print -r -- "$(( PASSED + FAILED )) checks: $PASSED passed, $FAILED failed"
(( FAILED == 0 ))
