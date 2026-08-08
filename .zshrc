export EDITOR=vim
set -o vi
bindkey -v

local CONFIG=${${(%):-%N}:A:h}

source "$CONFIG/zsh/prompt.zsh"

# Enable colors for ls
export CLICOLOR=1
# Set directories to blue (the 'ex' at the beginning)
export LSCOLORS="exfxcxdxbxegedabagacad"

alias ll='ls -Glah'
alias tac='tail -r'
alias t='tree'

export PATH="$PATH:$HOME/files/nvim/bin"
export PATH="$PATH:$HOME/.local/bin"
export PATH="$PATH:$HOME/.cargo/bin"

export PYENV_ROOT="$HOME/.pyenv"
[[ -d "$PYENV_ROOT/bin" ]] && export PATH="$PATH:$PYENV_ROOT/bin"
pyenv() { unfunction pyenv; eval "$(command pyenv init - zsh)"; pyenv "$@"; }

local ghcup="$HOME/.ghcup/env"
[[ -f "$ghcup" ]] && {
    export PATH="$PATH:$HOME/.ghcup/bin"
    . "$ghcup"
}

load_fireworks_key() {
  if [[ -z "$FIREWORKS_CODING_API_KEY" ]]; then
    export FIREWORKS_CODING_API_KEY="$(security find-generic-password -s "fireworks-coding-api-key" -w /Library/Keychains/System.keychain 2>/dev/null)" || return 1
  fi
}
load_fireworks_key >/dev/null 2>&1

alias oc='opencode'

export CFGS="$HOME/.config"
export VIRTUAL_ENV="$HOME/Developer/.venv"

function venv() {
  source "${VIRTUAL_ENV}/bin/activate"
}
function _git_branch() {
    git symbolic-ref --short HEAD 2>/dev/null
}

function _git_ticket() {
    _git_branch | grep -E '[-_]' | sed -E 's/^([^_-]+)[_-]([^_-]+).*/\1-\2/'
}

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
    nvim -c "DiffviewOpen ${arg}^! $file"

  elif [[ "$mode" == "range" ]]; then
    # show for range - e.g. a1b2c3d^..HEAD
    nvim -c "DiffviewFileHistory --range=${arg} $file"

  else
    # full history
    nvim -c "DiffviewFileHistory $file"
  fi
}

alias o=open

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
    elif [[ "$file" == "Developer" ]]; then
        _vd "$HOME/Developer/"
    elif [[ "$file" == "Downloads" ]]; then
        _vd "$HOME/Downloads/"
    elif [[ "$file" == "Movies" ]]; then
        _vd "$HOME/Movies/"
    elif [[ -n "$file" ]]; then
        _vd "$HOME/Developer/$file" || _vd "$file"
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
    elif [[ "$file" == "Developer" ]]; then
        cd "$HOME/Developer/"
    elif [[ "$file" == "Downloads" ]]; then
        cd "$HOME/Downloads/"
    elif [[ "$file" == "Movies" ]]; then
        cd "$HOME/Movies/"
    else
        cd "$HOME/Developer/$file" || cd "$file"
    fi
}


# defines __v / __p and their compdefs for the v and p functions above
source "$CONFIG/zsh/completions.zsh"

function gitc() {
    if git rev-parse -q --verify MERGE_HEAD >/dev/null; then
        git commit --no-edit
    else
        local commit="$@"
        local branch=$(_git_ticket)
        local commit_msg="${branch:+$branch }$commit"

        git commit -m "$commit_msg"
    fi
}

function gitcl() {
    git restore --staged .
    git restore .
    git clean -fd
}

function gitcp() {
    git cherry-pick $@
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
    git push && "$CFGS/zsh/git-pr-link.rb"
}

alias gg='git g'
alias pp='gitpp'
alias gpp='gitpp'
alias push='gitpp'

function master() {
    git symbolic-ref --short refs/remotes/origin/HEAD | cut -d/ -f2
}

function gitmm() {
    git fetch && git merge --no-edit origin/$(master)
    if [ $? -ne 0 ]; then
        local model=$(opencode models 2>/dev/null | grep "glm" | head -1 | awk '{print $1}')
        if [ -n "$model" ]; then
            opencode run --model "$model" "resolve merge conflicts, make sure to maintain code style"
        else
            opencode run "resolve merge conflicts, make sure to maintain code style"
        fi
        git merge --continue --no-edit
    fi
    git push
}

function gitrc() {
  git add .
  git rebase --continue
}

function gitsm() {
    git switch $(master) && git pull
}

function gitrh() {
    git fetch origin && git rebase origin/$(git branch --show-current)
}

function py() {
     venv && ipython --TerminalInteractiveShell.editing_mode=vi
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

function are-you-sure() {
  local prompt="${1:-Are you sure?}"
  read -q "REPLY?${prompt} [y/N] "
  local ans=$?
  echo
  return $ans
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

function gitwl() {
    git worktree list
}

function git-list-changes() {
    "$CFGS/zsh/git-list-changes.rb" $@
}

alias gs='git s'
alias glc='git-list-changes'

function git-review-reply() {
    "$CFGS/zsh/git-review-reply.rb" $@
}

function gitprs() {
    "$CFGS/zsh/git-prs.rb" $@
}

function xtest() {
    local tests
    tests=$(git diff --name-only --diff-filter=AM master...HEAD -- '*Test.java' '*Spec.java')

    if [[ -z "$tests" ]]; then
        echo "No changed test files found."
        return 0
    fi

    local test_args=()
    while IFS= read -r f; do
        local class
        class=$(echo "$f" | sed 's|.*/java/||; s|/|.|g; s|\.java$||')
        test_args+=("--tests" "$class")
    done <<< "$tests"

    echo "Running tests..."
    local errors
    errors=$(./gradlew test "${test_args[@]}" --console=plain --quiet 2>&1 | \
        grep -E -A5 -B2 'FAILED|Exception|Error|Caused by' | \
        grep -vE 'org.gradle|java.base|sun.reflect')

    if [[ -z "$errors" ]]; then
        echo
        echo "vvvvvvvvvvvvvvv"
        echo "All tests passed!"
        echo "^^^^^^^^^^^^^^^"
        echo
        return 0
    fi

    claude "Fix these test errors in the project files

  once fixed, push the changes to git upstream

  $errors"
}

function check() {
  echo "Running checkstyle..."
  local _check="[ERROR]"
  local _spot=".java:[line"
  local start=$SECONDS
  local errors=$(./gradlew --offline --parallel --build-cache \
      checkstyleMain checkstyleTest checkstyleTestData checkstyleTestFunctional \
      spotbugsMain spotbugsTest spotbugsTestData spotbugsTestFunctional \
      2>&1 | grep -F -e "${_check}" -e "${_spot}")
  local elapsed=$((SECONDS - start))

  if [[ -z "$errors" ]]; then
    echo
    echo vvvvvvvvvvvvvvv
    echo "All checks passed! (${elapsed}s)"
    echo ^^^^^^^^^^^^^^^
    echo
    return 0
  fi

  echo
  echo ---------------
  echo "Checkstyle violations (took ${elapsed}s):"
  echo "$errors"
  echo ---------------
  echo

  local model=$(opencode models 2>/dev/null | grep "glm" | head -1 | awk '{print $1}')
  local prompt="Fix these Checkstyle violations in the project files. Each line is filepath:line_number: [severity] description. Read each file, apply the fix, and save the changes.

  For spotbugs errors (the ones matching '.java:[line'), ONLY STRICTLY resolve them by slapping the annotation @SuppressFBWarnings(...) from edu.umd.cs.findbugs.annotations.SuppressFBWarnings, on a faulty line(s)

  For checkstyle errors (the ones matching '[ant:checkstyle] [ERROR]', resolve the actual cause

  use intellij mcp as much as possible

  $errors"
  if [ -n "$model" ]; then
    opencode run --model "$model" "$prompt"
  else
    opencode run "$prompt"
  fi

  if [[ -n $(git status --porcelain) ]]; then
    git add .
    gitpp "check"
    git push
  fi
}

function ytv() {
    if [[ -z "$1" ]]; then
        echo "usage: ytv <youtube-url> [more-urls...]" >&2
        return 1
    fi
    yt-dlp \
        -f "bestvideo*+bestaudio/best" \
        --merge-output-format mp4 \
        --embed-metadata --embed-thumbnail \
        -o "%(title)s.%(ext)s" \
        "$@"
}

function yta() {
    if [[ -z "$1" ]]; then
        echo "usage: yta <youtube-url> [more-urls...]" >&2
        return 1
    fi
    yt-dlp \
        -f "bestaudio/best" \
        --extract-audio --audio-format mp3 --audio-quality 0 \
        --embed-metadata --embed-thumbnail \
        -o "%(title)s.%(ext)s" \
        "$@"
}

function claude() {
    local prompt='
    - never squash git commits
    - when .md files in current directory, read them for context when prompted to do work on the project

    ## Java 

    1. when working with java code:
    - always use intellij mcp for all file lookups, navigation, inspection, and edits — reading files, finding symbols, searching code, writing changes. Only fall back to direct filesystem tools if the intellij mcp call fails or is unavailable
    - always do all changes in a worktree: if the user supplied a Jira ticket URL, follow the Jira ticket workflow below; otherwise ask the user for a ticket URL before starting any edits. If already inside a worktree, then dont create new one - just use the current one
    - never run tests
    - never read any .jars directly - use intellij mcp, or if unsuccessful, always ask person for follow-ups instead
    - every single class that extends EntityViewId (or really ends with Id) exposes an .id() method - instead of looking up the return value in .jars, just use that method directly every time. Let compilation checks wil figure out the correctness later

    2. after done writing code, split it into atomic git commits, one for each subfeature (or a single commit if change is homogeneous) and commit them. If git branch name matches regex "<(\w+)-(\d+)>.*" (where <...> is ticket name) then extract ticket name as commit msg prefix
    3. When running independent tool calls (reads, lookups, searches), batch them in parallel rather than sequentially

    ## Jira ticket workflow

    When the user supplies a Jira ticket URL:
    1. Fetch the ticket details using the Jira MCP tool
    2. Derive a branch name: <ticket-id>_<description> where description is max 15 chars, lowercase, words separated by underscores, summarising the ticket and users request
    3. If already inside of some git worktree, then proceed to step 4. Otherwise:
    3.1. Check if a worktree for that branch already exists (via "git worktree list") — if so, switch into it and skip creation. Otherwise:
    3.2. Run "git fetch origin" then create a git worktree at "../<current-dir-name>-<branch-name>" on a new branch based off origin/master: git worktree add -b <branch-name> <path> origin/master (e.g. if cwd is /dev/myrepo, worktree goes to /dev/myrepo-PROJ-123_fix_login)
    4. Do ALL subsequent work (edits, commits) inside that worktree — never touch the original project dir

    IMPORTANT: NEVER (and I mean under NO CIRCUMSTANCE) run the "review" skill UNLESS EXPLICITLY PROMPTED BY THE USER!!!!
    '

    command "$HOME/.local/bin/claude" \
        --permission-mode auto \
        --append-system-prompt "Always follow this rule: $prompt" "$@"
}

alias c='claude'

