# Insert a \x01 marker before every word boundary of a string (start, after a
# -_/. or space separator, or a camelCase hump) and lowercase the result, so a
# query char anchored to a marker only matches at a segment start.
function __fuzzy_mark() {
  local s="$1" ch prev="" out="" i
  for (( i=1; i<=${#s}; i++ )); do
    ch="${s[i]}"
    if [[ -z "$prev" || "$prev" == [-_/.\ ] || ( "$ch" == [A-Z] && "$prev" == [a-z0-9] ) ]]; then
      out+=$'\x01'"$ch"
    else
      out+="$ch"
    fi
    prev="$ch"
  done
  REPLY="${(L)out}"
}

# Boundary-aware fuzzy completion, ranked in three tiers:
#   1. literal prefix     - candidate starts with the typed query ("pr" -> "project")
#   2. start-anchored     - first typed letter is at the candidate's very start,
#                           remaining letters at later word boundaries
#                           ("pm" -> "project-main")
#   3. any-boundary       - first letter at any word boundary, deeper in the name
# Each typed letter must begin matching at a word boundary, so "no" never matches
# "eventstore". Non-alphanumeric query chars are ignored.
# Rank the given candidates against the current PREFIX and leave the ordered
# matches in the global array `reply` (literal-prefix, then start-anchored, then
# any-boundary). Empty query keeps every candidate in the given order.
function __fuzzy_rank() {
  reply=()
  local query="${(L)PREFIX//[^a-zA-Z0-9]/}"
  if [[ -z "$query" ]]; then
    reply=("$@")
    return
  fi
  local -a chars=(${(s::)query})
  local body="${(j:.*:)chars}"               # q0 .* q1 .* q2 ...
  local re_any=$'\x01'"$body"                # first letter at any boundary
  local re_anchor='^'$'\x01'"$body"          # first letter at the very start
  # Every tier below needs the query as an in-order subsequence, so throw the
  # rest away with one C-speed glob before the per-character marking loop runs.
  # Matters once the candidate list is every command on PATH, not just a dir.
  setopt localoptions extendedglob
  local glob="(#i)*${(j:*:)chars}*"
  set -- ${(M)@:#$~glob}
  local -a prefixed anchored others
  local cand REPLY
  for cand in "$@"; do
    if [[ "${(L)cand}" == "$query"* ]]; then
      prefixed+=("$cand")
      continue
    fi
    __fuzzy_mark "$cand"
    if [[ "$REPLY" =~ $re_anchor ]]; then
      anchored+=("$cand")
    elif [[ "$REPLY" =~ $re_any ]]; then
      others+=("$cand")
    fi
  done
  reply=("${prefixed[@]}" "${anchored[@]}" "${others[@]}")
}

function __fuzzy_compadd() {
  local -a reply
  __fuzzy_rank "$@"
  (( ${#reply} )) || return
  # Matches need not share the typed prefix, so force menu insertion instead of
  # the (possibly empty) longest-common-prefix that -U would otherwise insert.
  compstate[insert]=menu
  # -V names an unsorted group so compadd keeps our order (literal-prefix
  # matches first, fuzzy after) instead of re-sorting alphabetically.
  compadd -U -Q -V fuzzy -- "${reply[@]}"
}

typeset -g __fuzzy_auto=0

# Take every section's candidates at once: if the whole completion has exactly
# one distinct match, insert it immediately (no listing, no second TAB) and
# return 0 so the caller can skip the per-section groups. Returns 1 otherwise.
# Usage: __fuzzy_unique <candidate>...   (pass the union of all sections)
function __fuzzy_unique() {
  local -a reply
  __fuzzy_rank "$@"
  (( __fuzzy_auto )) && return 1
  # (u) dedups: the same name in two sections still inserts the same text.
  local -a matches=(${(u)reply})
  (( ${#matches} == 1 )) || return 1
  # `insert=1` inserts the first (only) match outright instead of listing it.
  compstate[insert]=1
  compadd -U -Q -- "$matches[1]"
  return 0
}

# Fuzzy-filter one labelled section and add it as its own visually separated
# group. Call once per section; sections display in call order, each under its
# own header. Usage: __fuzzy_group <tag> <header> <candidate>...
function __fuzzy_group() {
  local tag="$1" header="$2"; shift 2
  local -a reply
  __fuzzy_rank "$@"
  (( ${#reply} )) || return
  # Start menu selection immediately.  This makes the first TAB select the first
  # match instead of requiring a second TAB after the listing was displayed.
  # We never use `unambiguous`: fuzzy matches share no common prefix, so it would
  # replace the typed word with the empty common prefix and wipe it ("con" -> "").
  if (( __fuzzy_auto )); then
    # While typing, list matches without putting the completion menu into an
    # active state that can consume the next typed character.
    compstate[insert]=''
    compstate[list]='list force'
  else
    # Explicit TAB starts at the first ranked match, not the menu's last item.
    compstate[insert]=menu:1
  fi
  # -X gives the group a header line; -V keeps our order and separates it from
  # the other groups. -Q since candidates are already quoted-literal. Wrap the
  # header in a raw ANSI gray (bright-black) sequence so headers read as dim
  # labels; the listing prints these escapes verbatim.
  compadd -U -Q -X $'\e[90m'"$header"$'\e[0m' -V "$tag" -- "${reply[@]}"
}

function __v() {
  # three visually separated groups: shortcuts, ~/Developer projects, live cwd
  local -a here=( ${PWD}/*(N:t) )
  local -a shortcuts=( config .zshrc nvim Developer Downloads Movies )
  local -a developer=( $(ls $HOME/Developer/) )
  # a single match across all three groups completes straight away
  __fuzzy_unique $shortcuts $developer $here && return
  __fuzzy_group shortcuts  '=== shortcuts ==='       $shortcuts
  __fuzzy_group developer  $'\n=== ~/Developer ==='  $developer
  __fuzzy_group cwd        $'\n=== current dir ==='  $here
}

compdef __v v

function __p() {
  # same three groups as __v, but cwd is limited to directories
  local -a here=( ${PWD}/*(/N:t) )
  local -a shortcuts=( config nvim Developer Downloads Movies )
  local -a developer=( $(ls $HOME/Developer/) )
  # a single match across all three groups completes straight away
  __fuzzy_unique $shortcuts $developer $here && return
  __fuzzy_group shortcuts  '=== shortcuts ==='       $shortcuts
  __fuzzy_group developer  $'\n=== ~/Developer ==='  $developer
  __fuzzy_group cwd        $'\n=== current dir ==='  $here
}

compdef __p p

# Same boundary-aware matching for the command word itself, so "gitlc" reaches
# git-list-changes and "gwt" reaches gitwt. Functions starting with _ are the
# completion system's own (_git, _make, ...) and are never typed by hand.
function __cmds() {
  local -a funcs=( ${(k)functions[(I)[^_]*]} )
  local -a alis=( ${(k)aliases} )
  local -a bins=( ${(k)commands[(I)[^_]*]} )

  # a single match among your own functions and aliases runs straight away
  __fuzzy_unique $funcs $alis && return

  local hit=0
  __fuzzy_group functions '=== functions ==='   $funcs && hit=1
  __fuzzy_group aliases   $'\n=== aliases ==='  $alis  && hit=1
  __fuzzy_group commands  $'\n=== path ==='     $bins  && hit=1

  # nothing looked like a fuzzy match: hand back to stock command completion so
  # ./scripts, sudo <cmd>, PATH lookups and friends keep working as before
  (( hit )) || _command_names -e
}

compdef __cmds -command-

# Refresh project choices after each printable character typed as the argument
# to p() or v().  `list-choices` only redraws the candidates; __fuzzy_unique still
# inserts a lone match immediately, just as it does when TAB is pressed.
function __fuzzy_self_insert() {
  zle .self-insert
  [[ "$CURSOR" -eq "${#BUFFER}" ]] || return
  [[ "$BUFFER" == p\ * || "$BUFFER" == v\ * ]] || return
  local word="${BUFFER#* }"
  [[ -n "$word" && "$word" != *\ * ]] || return
  __fuzzy_auto=1
  zle list-choices
  __fuzzy_auto=0
}

zle -N __fuzzy_self_insert
bindkey -M emacs -R ' -~' __fuzzy_self_insert
bindkey -M viins -R ' -~' __fuzzy_self_insert
