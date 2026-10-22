#!/usr/bin/env bash
# Installs the skill as a symlink in ~/.claude/skills, a path read by Claude Code and OpenCode.
set -euo pipefail

SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/github-practices"
TARGET_DIR="${HOME:?HOME not set}/.claude/skills"
TARGET="${TARGET_DIR}/github-practices"

usage() {
    echo "usage: install.sh [--uninstall]" >&2
}

uninstall() {
    if [[ -L "$TARGET" ]]; then
        local points_to
        points_to="$(readlink "$TARGET")"
        # Only the link created by this repo is deleted. Another clone with the
        # same skill name points elsewhere and is not ours to touch.
        if [[ "$points_to" != "$SOURCE" ]]; then
            echo "error: $TARGET points to $points_to, not to $SOURCE; leaving it alone" >&2
            return 1
        fi
        rm "$TARGET"
        echo "removed symlink $TARGET (it pointed to $points_to)"
        return 0
    fi
    if [[ -e "$TARGET" ]]; then
        echo "error: $TARGET exists and is not a symlink; leaving it alone" >&2
        return 1
    fi
    echo "nothing to uninstall: $TARGET does not exist"
}

install() {
    if [[ ! -f "$SOURCE/SKILL.md" ]]; then
        echo "error: cannot find $SOURCE/SKILL.md; run install.sh from the repo" >&2
        return 1
    fi

    if [[ -L "$TARGET" ]]; then
        if [[ -d "$TARGET" ]] \
            && [[ "$(cd "$TARGET" && pwd -P)" == "$(cd "$SOURCE" && pwd -P)" ]]; then
            echo "already installed: $TARGET -> $SOURCE"
            return 0
        fi
        echo "error: $TARGET is already a symlink to $(readlink "$TARGET"), not to $SOURCE; leaving it alone" >&2
        return 1
    fi

    if [[ -e "$TARGET" ]]; then
        echo "error: $TARGET exists and is not a symlink; leaving it alone" >&2
        return 1
    fi

    mkdir -p "$TARGET_DIR"
    ln -s "$SOURCE" "$TARGET"
    echo "installed: $TARGET -> $SOURCE"
}

case "${1:-}" in
    "")
        install
        ;;
    --uninstall)
        uninstall
        ;;
    *)
        usage
        exit 2
        ;;
esac
