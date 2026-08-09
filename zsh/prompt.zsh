# fuzzy, case-insensitive autocomplete
zstyle ':completion:*' matcher-list '' 'm:{a-zA-Z}={A-Za-z}' 'r:|=*' 'l:|=* r:|=*'
autoload -Uz compinit
if [[ -n ~/.zcompdump(#qN.mh+24) ]]; then compinit; else compinit -C; fi

function git_prompt() {
  git rev-parse --is-inside-work-tree &>/dev/null || return

  local git_status
  git_status=$(git status --porcelain=v1 --branch 2>/dev/null)

  local branch ahead=0 behind=0
  local staged=0 modified=0 deleted=0 untracked=0

  while IFS= read -r line; do
    case "$line" in
      "## "*)
        branch=${line#\#\# }
        if [[ $line =~ ahead\ ([0-9]+) ]]; then
          ahead=${match[1]}
        fi
        if [[ $line =~ behind\ ([0-9]+) ]]; then
          behind=${match[1]}
        fi
        branch=${branch%%...*}
        ;;
      \?\?*) ((untracked++)) ;;
      *)
        [[ ${line:0:1} != " " && ${line:0:1} != "?" ]] && ((staged++))
        [[ ${line:1:1} != " " ]] && ((modified++))
        ;;
    esac
  done <<< "$git_status"

  local out="(git %F{green}$branch%f"
  [[ $ahead -gt 0 ]]     && out+=" %F{green}↑$ahead%f"
  [[ $behind -gt 0 ]]    && out+=" %F{red}↓$behind%f"
  [[ $staged -gt 0 ]]    && out+=" %F{green}+$staged%f"
  [[ $modified -gt 0 ]]  && out+=" %F{yellow}~$modified%f"
  [[ $untracked -gt 0 ]] && out+=" %F{cyan}?$untracked%f"
  out+=")"

  echo "$out"
}

typeset -g _git_prompt_cache=""
typeset -g _git_prompt_fd=""

function _async_git_callback() {
  local fd=$1
  IFS= read -r -u $fd _git_prompt_cache
  zle -F $fd 2>/dev/null; exec {fd}<&- 2>/dev/null
  _git_prompt_fd=""
  zle && zle reset-prompt
}

function _async_git_update() {
  if [[ -n $_git_prompt_fd ]]; then
    zle -F $_git_prompt_fd 2>/dev/null
    exec {_git_prompt_fd}<&- 2>/dev/null
    _git_prompt_fd=""
  fi
  exec {_git_prompt_fd}< <(git_prompt 2>/dev/null; echo)
  zle -F $_git_prompt_fd _async_git_callback
}

setopt prompt_subst
precmd_functions+=(_async_git_update)
PROMPT='| %F{245}%~%f ${_git_prompt_cache} %# '

