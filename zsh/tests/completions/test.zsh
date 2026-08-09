#!/usr/bin/env zsh
# Tests for zsh/completions.zsh — the fuzzy completion behind `v` and `p`.
#
# The helpers are pure apart from three touch points with zsh's completion
# system: they read $PREFIX, report matches via compadd, and steer the UI via
# $compstate. All three are stubbed below, so a test is just:
#   tab <query>; <the completion function>; assert on what came out.
#
# Run: zsh zsh/tests/completions/test.zsh   (or via zsh/tests/test.sh)

emulate -L zsh

typeset -g PASSED=0 FAILED=0

# ---------------------------------------------------------------- harness ---

# compadd/compstate/PREFIX stand-ins. ADDED is every match handed to compadd in
# order; GROUPS records one "<tag>:<match> <match>..." entry per compadd call so
# tests can assert on the grouping, not just the flat match list.
typeset -gA compstate
typeset -ga ADDED GROUPS
typeset -g PREFIX

compadd() {
  local tag="" ; local -a matches
  while (( $# )); do
    case "$1" in
      --) shift; matches=("$@"); break ;;
      -V) tag="$2"; shift 2 ;;
      -X) shift 2 ;;
      -*) shift ;;
      *)  matches=("$@"); break ;;
    esac
  done
  ADDED+=("${matches[@]}")
  GROUPS+=("${tag}:${(j: :)matches}")
}

# compdef is a compinit thing; completions.zsh calls it at source time.
compdef() { : }

# Reset to the state of a fresh TAB press on the word <query>. Pass "shown" as
# the second arg to simulate a second consecutive TAB (a listing is on screen).
tab() {
  PREFIX="$1"
  compstate=( insert unambiguous list '' old_list "${2-}" )
  ADDED=() GROUPS=()
}

suite() { print; print -r -- "$1"; }

check() {  # check <what> <expected> <actual>
  if [[ "$2" == "$3" ]]; then
    (( PASSED++ ))
    print -r -- "  ok   $1"
  else
    (( FAILED++ ))
    print -r -- "  FAIL $1"
    print -r -- "         expected: ${(V)2}"
    print -r -- "         actual:   ${(V)3}"
  fi
}

# Rank <candidates...> against the current PREFIX and return them space-joined.
ranked() {
  local -a reply
  __fuzzy_rank "$@"
  print -r -- "${(j: :)reply}"
}

source "${0:A:h}/../../completions.zsh"

# ------------------------------------------------------------ __fuzzy_mark ---

suite "__fuzzy_mark marks word boundaries"

typeset -g REPLY
__fuzzy_mark "Developer"
check "leading char is a boundary"     $'\x01developer'          "$REPLY"
__fuzzy_mark "myProject"
check "camelCase hump is a boundary"   $'\x01my\x01project'      "$REPLY"
__fuzzy_mark "proj-alpha"
check "char after a separator"         $'\x01proj-\x01alpha'     "$REPLY"
__fuzzy_mark "a.b c"
check "dot and space both separate"    $'\x01a.\x01b \x01c'      "$REPLY"

# ------------------------------------------------------------ __fuzzy_rank ---

suite "__fuzzy_rank ranks and filters"

cands=( eventstore project project-main .zshrc Downloads )

tab ""
check "empty query keeps input order" "eventstore project project-main .zshrc Downloads" "$(ranked $cands)"

tab "pr"
check "literal prefix matches"        "project project-main"     "$(ranked $cands)"

tab "pm"
check "start-anchored across humps"   "project-main"             "$(ranked $cands)"

tab "no"
check "mid-word letters never match"  ""                         "$(ranked $cands)"

tab "z"
check "non-alnum in name is skipped"  ".zshrc"                   "$(ranked $cands)"

tab ".z"
check "non-alnum in query is ignored" ".zshrc"                   "$(ranked $cands)"

tab "dm"
# dm-tool is a literal prefix; docs-main starts with the query's first letter;
# my-docs-main only matches from a boundary deeper in the name
check "tiers order the results" "dm-tool docs-main my-docs-main" "$(ranked my-docs-main docs-main eventstore dm-tool)"

# The subsequence glob that skips the marking loop must not drop real matches:
# it is case-insensitive, so a lowercase query still reaches a capitalised name.
tab "dev"
check "prefilter is case-insensitive"  "Developer"  "$(ranked Developer eventstore)"
tab "dvlpr"
check "  and spans the whole name"     "Developer"  "$(ranked Developer eventstore)"
tab "dx"
check "  while still dropping misses"  ""           "$(ranked Developer eventstore)"

# ---------------------------------------------------------- __fuzzy_unique ---

suite "__fuzzy_unique completes a lone match instantly"

tab "dow"
__fuzzy_unique config nvim Downloads Movies
check "returns 0 on exactly one match"  "0"           "$?"
check "  and inserts it"                "Downloads"   "${(j: :)ADDED}"
check "  via insert=1, not a listing"   "1"           "$compstate[insert]"

tab "nv"
__fuzzy_unique nvim Developer nvim   # same name in two sections
check "same name twice is one match"    "0"           "$?"
check "  and is added once"             "nvim"        "${(j: :)ADDED}"

tab "d"
__fuzzy_unique Developer Downloads
check "returns 1 on two matches"        "1"           "$?"
check "  and adds nothing"              ""            "${(j: :)ADDED}"
check "  leaving insert untouched"      "unambiguous" "$compstate[insert]"

tab "zzz"
__fuzzy_unique config nvim
check "returns 1 on no match"           "1"           "$?"
check "  and adds nothing"              ""            "${(j: :)ADDED}"

tab ""
__fuzzy_unique config
check "empty query, lone candidate"     "0"           "$?"
check "  is still inserted"             "config"      "${(j: :)ADDED}"

# ----------------------------------------------------------- __fuzzy_group ---

suite "__fuzzy_group lists, then menus on the second TAB"

tab "d"
__fuzzy_group shortcuts "=== shortcuts ===" Developer Downloads nvim
check "first TAB inserts nothing"     ""                     "$compstate[insert]"
check "  and forces the listing"      "list force"           "$compstate[list]"
check "  under the group tag"         "shortcuts:Developer Downloads" "${GROUPS[1]}"

tab "d" shown
__fuzzy_group shortcuts "=== shortcuts ===" Developer Downloads nvim
check "second TAB starts the menu"    "menu"                 "$compstate[insert]"

tab "zzz"
__fuzzy_group shortcuts "=== shortcuts ===" Developer Downloads
check "no matches adds no group"      ""                     "${(j: :)GROUPS}"
check "  and leaves the word alone"   "unambiguous"          "$compstate[insert]"

# ------------------------------------------------------------ __v and __p ---
# Real end-to-end wiring over a throwaway $HOME and $PWD.

typeset -g SANDBOX="$(mktemp -d)"
trap 'rm -rf "$SANDBOX"' EXIT INT TERM
mkdir -p "$SANDBOX"/Developer/{eventstore,my-docs} "$SANDBOX"/work/{nvim,notes}
touch "$SANDBOX"/work/readme.md
HOME="$SANDBOX"
cd "$SANDBOX/work"

suite "__p over shortcuts + ~/Developer + cwd"

tab "ev"
__p
check "lone ~/Developer hit inserts"   "eventstore"  "${(j: :)ADDED}"
check "  via insert=1"                 "1"           "$compstate[insert]"

tab "nv"
__p
check "shortcut+cwd dupe is one match" "nvim"        "${(j: :)ADDED}"

tab "no"
__p
check "cwd-only hit inserts"           "notes"       "${(j: :)ADDED}"

tab "d"
__p
check "several hits list as groups"    "shortcuts:Developer Downloads developer:my-docs" "${(j: :)GROUPS}"
check "  without inserting"            ""            "$compstate[insert]"

tab "re"
__p
check "cwd files are not offered"      ""            "${(j: :)ADDED}"

suite "__v also offers cwd files"

tab "re"
__v
check "readme.md completes"            "readme.md"   "${(j: :)ADDED}"

tab "zs"
__v
check ".zshrc shortcut is v-only"      ".zshrc"      "${(j: :)ADDED}"

# ---------------------------------------------------------------- __cmds ---
# The command word itself. Candidates come from three live sources, so the
# suite installs its own: throwaway functions and an alias here in the test
# shell, plus one executable reached through a sandboxed $PATH.

suite "__cmds completes the command word"

mkdir -p "$SANDBOX/bin"
print -r -- '#!/bin/sh' > "$SANDBOX/bin/zz-path-tool"
chmod +x "$SANDBOX/bin/zz-path-tool"

git-list-changes() { : }
gitwt() { : }
gitprs() { : }
_zzhidden() { : }            # completion-system style name, must stay hidden
alias zzalias='echo hi'

# __cmds hands unmatched words back to the stock command completion
typeset -g FELL_BACK
_command_names() { FELL_BACK="$*" }

# $PATH is scoped to the call so the cleanup trap keeps its own commands
cmds() {  # cmds <query>
  local -x PATH="$SANDBOX/bin"
  hash -r
  tab "$1"
  FELL_BACK=""
  __cmds
}

cmds gitlc
check "camelish query hits a function"  "git-list-changes" "${(j: :)ADDED}"
check "  and runs straight away"        "1"                "$compstate[insert]"

cmds gwt
check "initials reach gitwt"            "gitwt"            "${(j: :)ADDED}"

cmds gprs
check "  and gitprs"                    "gitprs"           "${(j: :)ADDED}"

cmds zzal
check "aliases are candidates too"      "zzalias"          "${(j: :)ADDED}"

cmds zzpt
check "PATH binaries list under path"   "commands:zz-path-tool" "${(j: :)GROUPS}"

cmds zzhid
check "_ functions are never offered"   ""                 "${(j: :)ADDED}"
check "  falling back instead"          "-e"               "$FELL_BACK"

cmds qqqzzz
check "no match adds nothing"           ""                 "${(j: :)ADDED}"
check "  and defers to stock completion" "-e"              "$FELL_BACK"

cmds git
check "a real hit does not fall back"   ""                 "$FELL_BACK"

# ---------------------------------------------------------------- results ---

print
print -r -- "$(( PASSED + FAILED )) checks: $PASSED passed, $FAILED failed"
(( FAILED == 0 ))
