export EDITOR=vim
set -o vi
bindkey -v

alias ll='ls -latrh'
alias tac='tail -r'

export PATH="$PATH:$HOME/files/nvim/bin"
export PATH="$PATH:$(npm bin -g)"
export PATH="$PATH:$HOME/.local/bin"
export PATH="$PATH:$HOME/.cargo/bin"

export PYENV_ROOT="$HOME/.pyenv"
[[ -d "$PYENV_ROOT/bin" ]] && {
    export PATH="$PATH:$PYENV_ROOT/bin"
    eval "$(pyenv init - zsh)"
}

function venv() {
  source "${VIRTUAL_ENV}/bin/activate"
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
    winname "$file"
    if [[ "$file" == ".zshrc" ]]; then
        nvim "$HOME/.zshrc"
    elif [[ "$file" == "config" ]]; then
        _vd "$HOME/.config/"
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

function gitpp() {
    local commit="$@"
    local branch=$(_git_ticket)
    local commit_msg="${branch:+$branch }$commit"

    git add .
    git commit -m "$commit_msg"
    git push
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

  if git show-ref --quiet refs/heads/"$branch"; then
    local changes=$(git status -s | wc -l)
    if [[ $changes -ne 0 ]]; then
      echo "can't switch to $branch because you have unstashed changes"
      return 1
    fi
    git switch "$branch"
    return
  fi

  local changes=$(git status -s | wc -l)
  if [[ $changes -ne 0 ]]; then
    git stash
  fi
  git switch master && git pull
  git switch -c "$branch" || git switch "$branch"
  if [[ $changes -ne 0 ]]; then
    git stash apply
  fi
}

function git-pr-desc() {
  if [[ -z "$X_BITBUCKET_USER" || -z "$X_BITBUCKET_PW" || -z "$X_BITBUCKET_REPOSITORY" ]]; then
    return
  fi

  local pr="$1"
  local is_short="$2"

  local repo="$X_BITBUCKET_REPOSITORY"
  local dir=$(basename $(pwd))
  local query="?fields=title,author.display_name,author.nickname,updated_on"
  local json=$(curl -s --request GET \
    --url "https://api.bitbucket.org/2.0/repositories/${repo}/${dir}/pullrequests/${pr}${query}" \
    --user "${X_BITBUCKET_USER}:${X_BITBUCKET_PW}" \
    --header 'Accept: application/json')

  local title=$(echo $json | jq -r '.title')
  local author=$(echo $json | jq '.author.display_name')
  local nickname=$(echo $json | jq -r '.author.nickname')
  local merge_time=$(echo $json | jq '.updated_on')

  local full_pr="https://bitbucket.org/${repo}/${dir}/pull-requests/${pr}"

  local ticket="$(echo "$title" | grep -oE '[A-Z]+-[0-9]+')"
  local full_ticket="https://${repo}.atlassian.net/browse/${ticket}"

  if [[ $is_short == 0 ]]; then
    echo "\t@${nickname} ${full_pr} (${title})"
    echo "\tTicket: $full_ticket"
    echo "\tMerged At: $merge_time"
  else
    echo "@${nickname} ${title} (${full_pr})"
  fi
}

function git-list-changes() {
  local is_short=0
  if [[ "$1" == '-s' ]]; then
    is_short=1
    shift
  fi

  local from="$1"
  local dir="$2"
  if [[ -z "$from" ]]; then
    echo "Usage:"
    echo "    git-list-changes <start-commit> [dir]"
    echo "Parameters:"
    echo "    start-commit (required) - a commit or range of commits (..) to display the diff for"
    echo "    dir          (optional) - if you need diff not for entire repository, but for a subdirectory instead"
    echo "Example:"
    echo "    git-list-changes d5bff459f963"
    echo "    git-list-changes d5bff459f963..e266dd4e6a55 albatross"
    return
  fi

  if [[ "$from" == *".."* ]]; then
    IFS='..' read -r from to <<< "$from"
  else
    to="origin/master"
  fi

  __glc() {
    local module="$1"
    local print_module_name=$2
    if [[ "$module" == '.' ]]; then
      return 0
    fi

    local result="$(git log origin/master --oneline "$from".."$to" --grep "^Merged" -- "$module")"
    if [[ -z "$result" ]]; then
      echo "No changes."
    else
      if [[ $print_module_name -eq 0 ]]; then
        echo
        echo ">>>> $module"
      fi
      git log --color=always origin/master --oneline "$from".."$to" --grep "^Merged" -- "$module" | while read line; do

        local pr_id=$(echo "$line" | awk -F'pull request #' '{print $2}' | awk -F')' '{print $1}')
        local desc=$(git-pr-desc $pr_id $is_short)
        if [[ $is_short == 0 ]]; then
          echo
          echo -e $line
          echo $desc
        else
          echo $desc
        fi

      done
    fi
  }

  if [[ ! -z "$dir" ]]; then
    __glc "$dir" 1
    return 0
  fi

  local modules="$(find . -maxdepth 2 -name build.gradle -exec dirname {} \;)"
  echo $modules | while read module; do
    __glc "$module" 0
  done
}

