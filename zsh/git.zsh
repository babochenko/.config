function _git_branch() { git symbolic-ref --short HEAD 2>/dev/null; }
function _git_ticket() { _git_branch | grep -E '[-_]' | sed -E 's/^([^_-]+)[_-]([^_-]+).*/\1-\2/'; }

function git-cherry-pick()        { git cherry-pick $@; }
function git-clean()              { git restore --staged .; git restore .; git clean -fd; }
function git-diff()               { git diff main --stat; }
function git-diff-full()          { nvim -c "DiffviewOpen HEAD"; }
function git-list-changes()       { "$CFGS/zsh/git-list-changes.rb" $@; }
function git-rebase-continue()    { git add .; git rebase --continue; }
function git-rebase-head()        { git fetch origin && git rebase origin/$(git branch --show-current); }
function git-rebase-interactive() { git rebase -i $@; }
function git-restore()            { git restore .; }
function git-switch-master()      { git switch $(master) && git pull; }
function git-worktree-list()      { git worktree list; }
function gitcc()                  { git add .; gitc $@; }
function gitp()                   { gitc $@; git push; }
function gitpp()                  { gitcc $@; git push && "$CFGS/zsh/git-pr-link.rb"; }

alias gd='git-diff'
alias gdd='git-diff-full'
alias gg='git g'
alias gitri='git-rebase-interactive'
alias gits='git s'
alias gitsm='git-switch-master'
alias gitwl='git-worktree-list'
alias gpp='gitpp'
alias grestore='git-restore'
alias gs='git s'
alias pp='gitpp'
alias push='gitpp'

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

function git-merge-master() {
    git fetch && git merge --no-edit origin/$(master)
    if [ $? -ne 0 ]; then
        local model=$(opencode models 2>/dev/null | grep "glm" | head -1 | awk '{print $1}')
        if [ -n "$model" ]; then
            opencode run --model "$model" "resolve merge conflicts, make sure to maintain code style"
        else
            opencode run "resolve merge conflicts, make sure to maintain code style"
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

function gitwt() {
  local name="$1"
  local base="${2:-master}"

  if [[ -z "$name" ]]; then
    echo "Usage: gitws <branch-name> [base-branch]"
    echo "creates a new worktree at ../branch-name from [base-branch | master]"
    return 1
  fi

  local target="../$(basename "$PWD")-${name}"
  if [[ -d "$target" ]]; then
    cd "$target"
    return 0
  fi

  git fetch origin >/dev/null 2>&1
  if git show-ref --quiet refs/heads/"$name"; then
    git worktree add "$target" "$name"
  else
    git worktree add -b "$name" "$target" "$base"
  fi
  cd "$target"
}

function gitwr() {
  local main_worktree
  main_worktree=$(git worktree list 2>/dev/null | awk 'NR==1{print $1}')

  if [[ -n "$main_worktree" && "$PWD" != "$main_worktree" ]]; then
    local current="$PWD"
    cd "$main_worktree"
    git worktree remove "$current"
    echo "$current → $PWD"
    return 0
  fi

  local target="$1"

  if [[ -z "$target" ]]; then
    echo "Usage: gitwr <worktree-path>"
    return 1
  fi

  # Must exist
  if [[ ! -d "$target" ]]; then
    echo "Directory does not exist: $target"
    return 1
  fi

  # Prefix must match current dir name
  local curdir
  curdir=$(basename "$PWD")

  local target_base
  target_base=$(basename "$target")

  if [[ "$target_base" != "${curdir}-"* ]]; then
    echo "Refusing: $target does not start with ${curdir}-"
    return 1
  fi

  # Must be a registered worktree
  if ! git worktree list | awk '{print $1}' | grep -Fxq "$(cd "$target" && pwd)"; then
    echo "Refusing: $target is not a registered worktree of this repo"
    return 1
  fi

  # Prevent removing current worktree
  if [[ "$(cd "$target" && pwd)" == "$(pwd)" ]]; then
    echo "Refusing: cannot remove current worktree"
    return 1
  fi

  git worktree remove "$target"
}

# Remove every worktree of this repo except the main one.
function gitwra() {
  are-you-sure "Remove ALL worktrees of this repo?" || return 1

  local main_worktree
  main_worktree=$(git worktree list 2>/dev/null | awk 'NR==1{print $1}')

  if [[ -z "$main_worktree" ]]; then
    echo "Not inside a git repository"
    return 1
  fi

  cd "$main_worktree"

  local wt
  git worktree list | awk 'NR>1{print $1}' | while IFS= read -r wt; do
    git worktree remove "$wt" && echo "removed $wt"
  done
}

