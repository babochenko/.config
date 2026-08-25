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

function git-worktree-list()      { git worktree list; }

alias gitwl='git-worktree-list'
