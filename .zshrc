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

# fuzzy, case-insensitive autocomplete
zstyle ':completion:*' matcher-list '' 'm:{a-zA-Z}={A-Za-z}' 'r:|=*' 'l:|=* r:|=*'
autoload -Uz compinit && compinit

function _git_branch() {
    git symbolic-ref --short HEAD 2>/dev/null
}

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

setopt prompt_subst
PROMPT='| %~ $(git_prompt) %# '

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

function gitrc() {
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

function gitwl() {
    git worktree list
}

function git-list-changes() {
    "$CFGS/zsh/git-list-changes.rb" $@
}

function git-review-reply() {
    "$CFGS/zsh/git-review-reply.rb" $@
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
  local errors=$(./gradlew check -x test -x testFunctional 2>&1 | grep -F -e "${_check}" -e "${_spot}")

  if [[ -z "$errors" ]]; then
    echo
    echo vvvvvvvvvvvvvvv
    echo "All checks passed!"
    echo ^^^^^^^^^^^^^^^
    echo
    return 0
  fi

  echo
  echo ---------------
  echo "Checkstyle violations:"
  echo "$errors"
  echo ---------------
  echo

  claude "Fix these Checkstyle violations in the project files. Each line is filepath:line_number: [severity] description. Read each file, apply the fix, and save the changes.

  For spotbugs errors (the ones matching '.java:[line'), ONLY STRICTLY resolve them by slapping the annotation @SuppressFBWarnings(...) from edu.umd.cs.findbugs.annotations.SuppressFBWarnings, on a faulty line(s)

  For checkstyle errors (the ones matching '[ant:checkstyle] [ERROR]', resolve the actual cause

  use intellij mcp as much as possible

  once fixed, push the changes to git upstream

  $errors"
}

function m() {
    dir="$HOME/Developer/marimo"
    mkdir -p "$dir"

    tmux new-session -d -s marimo "zsh -ic 'cd $dir && venv && marimo edit'"
    tmux ls
}

function claude() {
    local prompt='
    ## Coding

    1. when working with java code:
    - always use intellij mcp for all file lookups, navigation, inspection, and edits — reading files, finding symbols, searching code, writing changes. Only fall back to direct filesystem tools if the intellij mcp call fails or is unavailable
    - always do all changes in a worktree: if the user supplied a Jira ticket URL, follow the Jira ticket workflow below; otherwise ask the user for a ticket URL before starting any edits. If already inside a worktree, then dont create new one - just use the current one
    2. after done writing code, split it into atomic git commits, one for each subfeature (or a single commit if change is homogeneous) and commit them. If git branch name matches regex "<(\w+)-(\d+)>.*" (where <...> is ticket name) then extract ticket name as commit msg prefix
    3. When running independent tool calls (reads, lookups, searches), batch them in parallel rather than sequentially
    4. When the user says "gitpp": stage all changes, write a concise summary commit message, and push to upstream — do this immediately without asking for confirmation

    ## Jira ticket workflow

    When the user supplies a Jira ticket URL:
    1. Fetch the ticket details using the Jira MCP tool
    2. Derive a branch name: <ticket-id>_<description> where description is max 15 chars, lowercase, words separated by underscores, summarising the ticket and users request
    3. If already inside of some git worktree, then proceed to step 4. Otherwise:
    3.1. Check if a worktree for that branch already exists (via "git worktree list") — if so, switch into it and skip creation. Otherwise:
    3.2. Run "git fetch origin" then create a git worktree at "../<current-dir-name>-<branch-name>" on a new branch based off origin/master: git worktree add -b <branch-name> <path> origin/master (e.g. if cwd is /dev/myrepo, worktree goes to /dev/myrepo-PROJ-123_fix_login)
    4. Do ALL subsequent work (edits, commits) inside that worktree — never touch the original project dir
    '

    command "$HOME/.local/bin/claude" --append-system-prompt "Always follow this rule: $prompt" "$@"
}

alias c='claude'

