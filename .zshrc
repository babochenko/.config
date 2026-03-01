export EDITOR=vim
set -o vi
bindkey -v

alias ll='ls -la'
alias tac='tail -r'

export PATH="$PATH:$HOME/files/nvim/bin"
export PATH="$PATH:$HOME/.local/bin"
export PATH="$PATH:$HOME/.cargo/bin"

export PYENV_ROOT="$HOME/.pyenv"
[[ -d "$PYENV_ROOT/bin" ]] && {
    export PATH="$PATH:$PYENV_ROOT/bin"
    eval "$(pyenv init - zsh)"
}

local ghcup="$HOME/.ghcup/env"
[[ -f "$ghcup" ]] && {
    export PATH="$PATH:$HOME/.ghcup/bin"
    . "$ghcup"
}

export CFGS="$HOME/.config"
export VIRTUAL_ENV="$HOME/Developer/.venv"

function venv() {
  source "${VIRTUAL_ENV}/bin/activate"
}

function py() {
  venv && python
}

# fuzzy, case-insensitive autocomplete
zstyle ':completion:*' matcher-list '' 'm:{a-zA-Z}={A-Za-z}' 'r:|=*' 'l:|=* r:|=*'
autoload -Uz compinit && compinit

function _git_branch() {
    git symbolic-ref --short HEAD 2>/dev/null
}

function _prompt_git_branch() {
    local branch="$(_git_branch)"
    if [[ -n "$branch" ]]; then
        echo "(git %F{green}${branch}%F{white}) "
    fi
}

function _git_ticket() {
    _git_branch | grep -E '[-_]' | sed -E 's/^([^_-]+)[_-]([^_-]+).*/\1-\2/'
}

setopt prompt_subst
PROMPT='| %~ $(_prompt_git_branch)%# '

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
    if [[ "$file" == ".zshrc" ]]; then
        nvim "$HOME/.zshrc"
    elif [[ "$file" == "config" ]]; then
        _vd "$HOME/.config/"
    elif [[ "$file" == "nvim" ]]; then
        _vd "$HOME/.config/nvim/"
    elif [[ -n "$file" ]]; then
        _vd "$HOME/Developer/$file"
    else
        nvim
    fi
}

function p() {
    local file="$1"
    if [[ "$file" == "nvim" ]]; then
        cd "$HOME/.config/nvim/"
    elif [[ "$file" == "config" ]]; then
        cd "$HOME/.config/"
    else
        cd "$HOME/Developer/$file"
    fi
}

function __v() {
  compadd config .zshrc nvim $(ls $HOME/Developer/)
}

compdef __v v

function __p() {
  compadd config nvim $(ls $HOME/Developer/)
}

compdef __p p

function gitc() {
    local commit="$@"
    local branch=$(_git_ticket)
    local commit_msg="${branch:+$branch }$commit"

    git commit -m "$commit_msg"
}

function gitcc() {
    git add .
    gitc $@
}

function gitp() {
    gitc $@
    git push
}

function gitpp() {
    gitcc $@
    git push
}

function master() {
    git symbolic-ref --short refs/remotes/origin/HEAD | cut -d/ -f2
}

function gitmm() {
    git fetch && git merge --no-edit origin/$(master) && git push
}

function gitmc() {
  git merge --continue
}

function gitsm() {
    git switch $(master) && git pull
}

function gitrh() {
    git fetch origin && git rebase origin/$(git branch --show-current)
}

function ipy() {
     venv; ipython --TerminalInteractiveShell.editing_mode=vi
}

function gitsw() {
  local branch="$1"
  if [[ -z "$branch" ]]; then
    echo 'Usage: gitsw <branch>  - applies all pending changes on top of another branch'
    return 1
  fi

  local changes=$(git status -s | wc -l)
  if [[ $changes -ne 0 ]]; then
    git stash
  fi

  if git show-ref --quiet refs/heads/"$branch"; then
    git switch "$branch"
  else
      git switch $(master) && git pull
    git switch -c "$branch" || git switch "$branch"
  fi

  if [[ $changes -ne 0 ]]; then
    git stash apply
  fi
}

function git-list-changes() {
    "$CFGS/zsh/git-list-changes.rb" $@
}

function check() {
    "$CFGS/zsh/gradle-checkstyle.rb" $@
}

