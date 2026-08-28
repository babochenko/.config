#!/bin/sh
# Behind option+q: exit 0 only when this pane is a `t` terminal positively
# known to be sitting at an idle prompt. That is the one case opendash closes
# the session instead of detaching from it.
#
# usage: idle-check.sh <session-name> <pane-tty> <pane-pid>
#
# Idleness is decided from the foreground process group on the pane's tty, not
# from the process name: `./gradlew test` reports the pane's current command as
# "bash", and a shell *function* that shells out (check) reports "zsh", so a
# name test closes terminals out from under running builds.
#
# Anything unexpected -- no ps output, an unreadable tty, a shell that does not
# hold the terminal -- is treated as busy, because detaching from an idle
# terminal is a harmless mistake and killing a busy one is not.

state="${OPENDASH_STATE:-$HOME/.local/state/opendash}"
log="$state/idle-check.last"

verdict() {                      # $1 = exit code, $2 = why
    [ -d "$state" ] && {
        printf 'time=%s session=%s tty=%s pane_pid=%s verdict=%s (%s)\n%s\n' \
            "$(date +%H:%M:%S)" "$1" "$2" "$3" "$5" "$6" "$snapshot" >"$log" 2>/dev/null
    }
    exit "$4"
}

session="$1"
tty="${2#/dev/}"
me="$3"
snapshot=""

case "$session" in
    sh-*) ;;
    *) verdict "$session" "$tty" "$me" 1 detach "not a t terminal" ;;
esac

[ -n "$tty" ] && [ -n "$me" ] || verdict "$session" "$tty" "$me" 1 detach "missing tty or pid"

snapshot=$(ps -t "$tty" -o pid=,pgid=,stat=,args= 2>/dev/null)
[ -n "$snapshot" ] || verdict "$session" "$tty" "$me" 1 detach "no ps output for tty"

# Close only when the shell itself holds the terminal and nothing else does.
printf '%s\n' "$snapshot" | awk -v me="$me" '
    $3 ~ /\+/ && $1 == me  { shell_has_terminal = 1 }
    $3 ~ /\+/ && $1 != me  { something_running = 1 }
    END { exit !(shell_has_terminal && !something_running) }
' && verdict "$session" "$tty" "$me" 0 close "idle prompt" \
  || verdict "$session" "$tty" "$me" 1 detach "something running, or shell not in foreground"
