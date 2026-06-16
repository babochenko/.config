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
function __fuzzy_compadd() {
  local query="${(L)PREFIX//[^a-zA-Z0-9]/}"
  if [[ -z "$query" ]]; then
    compadd -- "$@"
    return
  fi
  local -a chars=(${(s::)query})
  local body="${(j:.*:)chars}"               # q0 .* q1 .* q2 ...
  local re_any=$'\x01'"$body"                # first letter at any boundary
  local re_anchor='^'$'\x01'"$body"          # first letter at the very start
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
  local -a matches=("${prefixed[@]}" "${anchored[@]}" "${others[@]}")
  (( ${#matches} )) || return
  # Matches need not share the typed prefix, so force menu insertion instead of
  # the (possibly empty) longest-common-prefix that -U would otherwise insert.
  compstate[insert]=menu
  # -V names an unsorted group so compadd keeps our order (literal-prefix
  # matches first, fuzzy after) instead of re-sorting alphabetically.
  compadd -U -Q -V fuzzy -- "${matches[@]}"
}

function _comp() {
  local cmd=$1
  shift

  eval "
  _${cmd}_complete() {
    __fuzzy_compadd \$@
  }

  compdef _${cmd}_complete ${cmd}
  "
}

