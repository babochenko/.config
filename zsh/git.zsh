function _git_branch() { git symbolic-ref --short HEAD 2>/dev/null; }
function _git_ticket() { _git_branch | grep -E '[-_]' | sed -E 's/^([^_-]+)[_-]([^_-]+).*/\1-\2/'; }
function master() { git symbolic-ref --short refs/remotes/origin/HEAD | cut -d/ -f2; }

function git-history() {
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
    nvim -c "DiffviewOpen ${arg}^! $file"

  elif [[ "$mode" == "range" ]]; then
    # show for range - e.g. a1b2c3d^..HEAD
    nvim -c "DiffviewFileHistory --range=${arg} $file"

  else
    # full history
    nvim -c "DiffviewFileHistory $file"
  fi
}
alias gh='git-history'

function git-commit() {
    if git rev-parse -q --verify MERGE_HEAD >/dev/null; then
        git commit --no-edit
    else
        local commit="$@"
        local branch=$(_git_ticket)
        local commit_msg="${branch:+$branch }$commit"

        git commit -m "$commit_msg"
    fi
}
alias gitc='git-commit'

# `git g`, but only 10 commits at a time: LINES makes less treat the screen as
# 11 rows, so the log opens inline under the prompt and stays navigable with the
# usual less keys (space/j/k/G, q to quit). extra args are forwarded to git log
# (e.g. `gg master`, `gg -- some/file`)
function git-log() {
  local lines=${GIT_LOG_LINES:-10}

  if [[ ! -t 1 ]]; then
    git g "$@"
    return
  fi

  git g --color=always "$@" | LINES=$((lines + 1)) less -RSXF
}

function git-merge-master() {
    git fetch && git merge --no-edit origin/$(master)
    if [ $? -ne 0 ]; then
        local model=$(opencode models 2>/dev/null | grep "glm" | head -1 | awk '{print $1}')
        local prompt="resolve merge conflicts, make sure to maintain code style"
        if [ -n "$model" ]; then
            opencode run --model "$model" "$prompt"
        else
            opencode run "$prompt"
        fi
        git add . && git merge --continue --no-edit
    fi
    git push
}
alias gitmm='git-merge-master'

function git-switch() {
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
alias gitsw='git-switch'

# uncommitted changes - staged, unstaged and untracked files. pass a base to
# compare against something else instead (e.g. `gd master`). read-only:
# untracked files are collected through a throwaway copy of the index, so the
# repo is never touched
function git-status() {
  local base="${1:-HEAD}"
  if ! git rev-parse --verify --quiet "$base^{commit}" >/dev/null; then
    echo "unknown revision: $base"
    return 1
  fi

  local merge_base
  merge_base=$(git merge-base "$base" HEAD 2>/dev/null)
  [[ -z "$merge_base" ]] && merge_base="$base"

  local index=${$(git rev-parse --git-path index):A}
  local tmp_index=""
  local untracked=("${(@f)$(git ls-files --others --exclude-standard)}")

  if [[ -n "$untracked" ]] && tmp_index=$(mktemp) && cp "$index" "$tmp_index" 2>/dev/null; then
    index="$tmp_index"
    GIT_INDEX_FILE="$index" git add -N -- $untracked
  fi

  if GIT_INDEX_FILE="$index" git diff --quiet "$merge_base"; then
    echo "no changes vs $base"
  else
    GIT_INDEX_FILE="$index" git diff --stat "$merge_base"
  fi

  [[ -n "$tmp_index" ]] && rm -f "$tmp_index"
}
alias gs='git-status'

function git-cherry-pick()        { git cherry-pick $@; }
function git-clean()              { git restore --staged .; git restore .; git clean -fd; }
function git-diff()          { nvim -c "DiffviewOpen HEAD"; }
function git-list-changes()       { "$CFGS/zsh/git-list-changes.rb" $@; }
function git-rebase-continue()    { git add .; git rebase --continue; }
function git-rebase-head()        { git fetch origin && git rebase origin/$(git branch --show-current); }
function git-rebase-interactive() { git rebase -i $@; }
function git-restore()            { git restore .; }
function git-switch-master()      { git switch $(master) && git pull; }
function gitcc()                  { git add .; gitc $@; }
function gitp()                   { gitc $@; git push; }
function gitpp()                  { gitcc $@; git push && "$CFGS/zsh/git-pr-link.rb"; }

alias gd='git-diff'
alias gg='git-log'
alias gitri='git-rebase-interactive'
alias gits='git s'
alias gitsm='git-switch-master'
alias gpp='gitpp'
alias grestore='git-restore'
alias pp='gitpp'
alias push='gitpp'

