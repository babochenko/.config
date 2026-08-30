export EDITOR=vim
set -o vi
bindkey -v

local CONFIG=${${(%):-%N}:A:h}

source "$CONFIG/zsh/prompt.zsh"

# Enable colors for ls
export CLICOLOR=1
# Set directories to blue (the 'ex' at the beginning)
export LSCOLORS="exfxcxdxbxegedabagacad"

function ll() {
    ls -Glaht | head -1
    ls -Glahtd */
    ls -Glahtp | tail -n +2 | grep -v '/$'
}

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

alias oc='opencode --auto --agent myagent'

# dashboard for opencode instances running in the background
alias opendash="$CONFIG/opendash/opendash"
alias oo="opendash"

export CFGS="$HOME/.config"
export VIRTUAL_ENV="$HOME/Developer/.venv"

function watch() {
    local -a old new
    local i max

    printf '\033[?25l'

    trap 'printf "\033[?25h"; return' INT TERM EXIT

    while true; do
        new=("${(@f)$(eval "$*")}")
        max=$(( ${#old[@]} > ${#new[@]} ? ${#old[@]} : ${#new[@]} ))

        for (( i = 1; i <= max; i++ )); do
            if [[ "${old[i]-}" != "${new[i]-}" ]]; then
                printf '\033[%d;1H\033[2K%s' "$i" "${new[i]-}"
            fi
        done

        old=("${new[@]}")
        sleep 0.5
    done
}

function venv() {
  source "${VIRTUAL_ENV}/bin/activate"
}

alias o=open

function v() {
    function _vd() {
        # vd - vim open dir
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
        nvim $@
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
source "$CONFIG/zsh/git.zsh"
source "$CONFIG/zsh/git-worktree.zsh"

function ipy() { venv && ipython --TerminalInteractiveShell.editing_mode=vi; }
function py() { venv && python3 $@; }

function jupyter-notebook() {
    venv

    if pgrep -f "jupyter-notebook" >/dev/null; then
        echo "Jupyter already running"
        return
    fi

    nohup jupyter notebook >/dev/null 2>&1 &
    disown
}

function jupyter-notebook-stop() { pkill -f "jupyter-notebook"; }

function are-you-sure() {
  local prompt="${1:-Are you sure?}"
  read -q "REPLY?${prompt} [y/N] "
  local ans=$?
  echo
  return $ans
}

function check() {
  echo "Running checkstyle..."
  local _check="[ERROR]"
  local _spot=".java:[line"
  local start=$SECONDS
  local output rc
  output=$(./gradlew --parallel --build-cache \
      checkstyleMain checkstyleTest checkstyleTestData checkstyleTestFunctional \
      spotbugsMain spotbugsTest spotbugsTestData spotbugsTestFunctional \
      2>&1)
  rc=$?
  local elapsed=$((SECONDS - start))
  local errors=$(echo "$output" | grep -F -e "${_check}" -e "${_spot}")

  if [[ -z "$errors" && $rc -ne 0 ]]; then
    echo
    echo vvvvvvvvvvvvvvv
    echo "BUILD FAILED (took ${elapsed}s):"
    echo "$output" | tail -30
    echo ^^^^^^^^^^^^^^^
    echo
    return 1
  fi

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

function yt-video() {
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

function yt-audio() {
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

