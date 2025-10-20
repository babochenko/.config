export EDITOR=vim
set -o vi
bindkey -v

alias ll='ls -latrh'

function tac() {
  if [ "$#" -eq 0 ]; then set -- -; fi
  for f in "$@"; do
    [ "$f" = "-" ] && awk '{a[NR]=$0} END{for(i=NR;i>0;i--)print a[i]}' \
                   || awk '{a[NR]=$0} END{for(i=NR;i>0;i--)print a[i]}' "$f"
  done
}

function _has() {
    command -v "$1" >/dev/null 2>&1;
}

export PATH="$PATH:$HOME/files/nvim/bin"
export PATH="$PATH:$(npm bin -g)"
export PATH="$PATH:$HOME/.local/bin"
export PATH="$PATH:$HOME/.cargo/bin"

_has pyenv && {
    export PYENV_ROOT="$HOME/.pyenv"
    [[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"
    eval "$(pyenv init - zsh)"
}

function venv() {
  source "${VIRTUAL_ENV}/bin/activate"
}

# fuzzy, case-insensitive autocomplete
zstyle ':completion:*' matcher-list '' 'm:{a-zA-Z}={A-Za-z}' 'r:|=*' 'l:|=* r:|=*'
autoload -Uz compinit && compinit

function __prompt_git_branch() {
  local branch="$(git symbolic-ref --short HEAD 2>/dev/null)"
  if [[ -z "$branch" ]]; then
    return
  fi

  echo "(git %F{green}${branch}%F{white}) "
}

setopt prompt_subst
PROMPT='| %~ $(__prompt_git_branch)%# '

function gd() {
    nvim -c "DiffviewOpen HEAD"
}

function gh() {
  local file="" mode="history" arg=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -c|--commit) mode="commit"; arg="$2"; shift 2;;
      -r|--range)  mode="range";  arg="$2"; shift 2;;
      *) file="$1"; shift;;
    esac
  done

  if [[ "$mode" == "commit" ]]; then
    # show just that commit for the file
    nvim -c "DiffviewOpen ${arg}^! -- $file"

  elif [[ "$mode" == "range" ]]; then
    # show for range - e.g. a1b2c3d^..HEAD
    nvim -c "DiffviewFileHistory --range=${arg} -- $file"

  else
    # full history
    nvim -c "DiffviewFileHistory -- $file"
  fi
}

function v() {
    # vd - vim open dir
    function _vd() {
        local d="$1"
        pushd . >/dev/null
        cd "$d" && nvim
        popd . >/dev/null
    }

    local file="$1"
    winname "$file"
    if [[ "$file" == ".zshrc" ]]; then
        nvim "$HOME/.zshrc"
    elif [[ "$file" == "nvim" ]]; then
        _vd "$HOME/.config/nvim/"
    else
        _vd "$HOME/Developer/$file"
    fi
}

function p() {
    local file="$1"
    winname "$file"
    if [[ "$file" == "nvim" ]]; then
        cd "$HOME/.config/nvim/"
    else
        cd "$HOME/Developer/$file"
    fi
}

function __v() {
  compadd .zshrc nvim $(ls $HOME/Developer/)
}

compdef __v v

function __p() {
  compadd nvim $(ls $HOME/Developer/)
}

compdef __p p

function gitpp() {
  local commit="$@"
  git add .
  git commit -m "$commit"
  git push
}

function ipy() {
     venv; ipython --TerminalInteractiveShell.editing_mode=vi
}

git config --global alias.s status
git config --global alias.g \
"log --graph --oneline --decorate --date=format:'%Y-%m-%d %H:%M' --pretty=format:'%C(auto)%h %Cgreen%ad %C(auto)%d %s'"

