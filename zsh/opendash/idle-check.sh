#!/bin/sh
# Behind option+q: exit 0 when this pane is a `t` terminal sitting at an idle
# prompt, which is the only case opendash closes instead of detaching.
#
# usage: idle-check.sh <session-name> <pane-tty> <pane-pid>
#
# Idleness is decided by pid, not by process name: running a shell script
# (./gradlew test) makes tmux report the pane's current command as "bash", and a
# name test would close the terminal out from under the build. A pane is idle
# when the only process in its foreground process group is its own shell.

case "$1" in
    sh-*) ;;                      # a t terminal; may be closable
    *) exit 1 ;;                  # an opencode TUI: always just detach
esac

ps -t "${2#/dev/}" -o pid=,stat= |
    awk -v me="$3" '$2 ~ /\+/ && $1 != me { busy = 1 } END { exit busy }'
