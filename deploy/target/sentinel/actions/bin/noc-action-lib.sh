#!/usr/bin/env bash
set -euo pipefail
umask 022

ALLOW_DIR=/etc/noc-sentinel/actions
ARG_RE='^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$'

refuse() {
    printf 'refused: %s\n' "$*" >&2
    exit 3
}

allow_value() {
    local action="$1" key="$2" file="$ALLOW_DIR/$1.allow" mode
    [[ "$key" =~ $ARG_RE ]] || refuse "argument is not a plain name"
    [[ -f "$file" && ! -L "$file" ]] || refuse "$file does not exist, so this host does not allow $action"
    [[ "$(stat -c %u "$file")" == 0 ]] || refuse "$file is not owned by root"
    mode=$(stat -c %a "$file")
    (( (8#$mode & 8#022) == 0 )) || refuse "$file is writable by group or others"
    awk -v key="$key" '
        $1 == key { print (NF > 1 ? $2 : "-"); found = 1; exit }
        END { exit found ? 0 : 1 }
    ' "$file" || refuse "$key is not listed in $file"
}

plain_directory() {
    local dir="$1"
    [[ "$dir" == /* && "$dir" != / ]] || refuse "allow file must give an absolute directory, not /"
    [[ -d "$dir" && ! -L "$dir" ]] || refuse "$dir is not a directory"
}

service_unit() {
    [[ "$1" == *.service && "$1" != *@* ]] || refuse "$1 is not a plain .service unit"
}
