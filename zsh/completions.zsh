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

# Fuzzy-filter one labelled section and add it as its own visually separated
# group. Call once per section; sections display in call order, each under its
# own header. Usage: __fuzzy_group <tag> <header> <candidate>...
function __fuzzy_group() {
  local tag="$1" header="$2"; shift 2
  local -a reply
  __fuzzy_rank "$@"
  (( ${#reply} )) || return
  # First TAB just lists; a second consecutive TAB (the previous listing is still
  # on screen -> old_list is "shown") starts menu selection to cycle matches.
  # We never use `unambiguous`: fuzzy matches share no common prefix, so it would
  # replace the typed word with the empty common prefix and wipe it ("con" -> "").
  if [[ "$compstate[old_list]" == shown ]]; then
    compstate[insert]=menu
  else
    # Insert nothing so the typed word stays intact and can be corrected by hand.
    # `list force` guarantees the listing shows.
    compstate[insert]=''
    compstate[list]='list force'
  fi
  # -X gives the group a header line; -V keeps our order and separates it from
  # the other groups. -Q since candidates are already quoted-literal. Wrap the
  # header in a raw ANSI gray (bright-black) sequence so headers read as dim
  # labels; the listing prints these escapes verbatim.
  compadd -U -Q -X $'\e[90m'"$header"$'\e[0m' -V "$tag" -- "${reply[@]}"
}

