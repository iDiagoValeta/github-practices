#!/usr/bin/env bash
# Installs the skill as a symlink in the skills directory of each agent named
# on the command line. One repo and one skill folder serve Claude Code, Codex,
# Cursor, Gemini CLI, GitHub Copilot, OpenCode, Windsurf, ZCode and any agent
# that reads the open SKILL.md format; only the directory changes.
set -euo pipefail

SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/github-practices"
HOME_DIR="${HOME:?HOME not set}"

usage() {
    cat >&2 <<'EOF'
usage: install.sh AGENT...
       install.sh --uninstall AGENT...
       install.sh --list

AGENT: claude-code, codex, cursor, gemini-cli, github-copilot, opencode,
       windsurf, zcode
EOF
}

agent_dir() {
    case "$1" in
        claude-code) echo ".claude/skills" ;;
        codex) echo ".agents/skills" ;;
        cursor) echo ".cursor/skills" ;;
        gemini-cli) echo ".gemini/skills" ;;
        github-copilot) echo ".copilot/skills" ;;
        opencode) echo ".config/opencode/skills" ;;
        windsurf) echo ".codeium/windsurf/skills" ;;
        zcode) echo ".zcode/skills" ;;
        *) return 1 ;;
    esac
}

is_agent() {
    agent_dir "$1" >/dev/null
}

target_of() {
    echo "$HOME_DIR/$(agent_dir "$1")/github-practices"
}

install_agent() {
    local target_dir
    target_dir="$HOME_DIR/$(agent_dir "$1")"
    local target="$target_dir/github-practices"

    if [[ ! -f "$SOURCE/SKILL.md" ]]; then
        echo "error: cannot find $SOURCE/SKILL.md; run install.sh from the repo" >&2
        return 1
    fi

    if [[ -L "$target" ]]; then
        if [[ -d "$target" ]] \
            && [[ "$(cd "$target" && pwd -P)" == "$(cd "$SOURCE" && pwd -P)" ]]; then
            echo "already installed: $target -> $SOURCE"
            return 0
        fi
        echo "error: $target is already a symlink to $(readlink "$target"), not to $SOURCE; leaving it alone" >&2
        return 1
    fi

    if [[ -e "$target" ]]; then
        echo "error: $target exists and is not a symlink; leaving it alone" >&2
        return 1
    fi

    mkdir -p "$target_dir" || return 1
    ln -s "$SOURCE" "$target" || return 1
    echo "installed: $target -> $SOURCE"
}

uninstall_agent() {
    local target_dir
    target_dir="$HOME_DIR/$(agent_dir "$1")"
    local target="$target_dir/github-practices"

    if [[ -L "$target" ]]; then
        local points_to
        points_to="$(readlink "$target")"
        # Only the link created by this repo is deleted. Another clone with the
        # same skill name points elsewhere and is not ours to touch. The repo may
        # be reached through a symlinked path, so the resolved directories also
        # count as a match, not just the raw readlink string.
        if [[ "$points_to" != "$SOURCE" ]] \
            && ! { [[ -d "$target" ]] && [[ -d "$SOURCE" ]] \
                && [[ "$(cd "$target" && pwd -P)" == "$(cd "$SOURCE" && pwd -P)" ]]; }; then
            echo "error: $target points to $points_to, not to $SOURCE; leaving it alone" >&2
            return 1
        fi
        rm "$target" || return 1
        echo "removed symlink $target (it pointed to $points_to)"
        return 0
    fi
    if [[ -e "$target" ]]; then
        echo "error: $target exists and is not a symlink; leaving it alone" >&2
        return 1
    fi
    echo "nothing to uninstall: $target does not exist"
}

case "${1:-}" in
    "")
        usage
        exit 2
        ;;
    --list)
        if [[ $# -ne 1 ]]; then
            usage
            exit 2
        fi
        for agent in claude-code codex cursor gemini-cli github-copilot opencode windsurf zcode; do
            printf '%s\t%s\n' "$agent" "$(target_of "$agent")"
        done
        exit 0
        ;;
    --uninstall)
        shift
        action=uninstall_agent
        ;;
    *)
        action=install_agent
        ;;
esac

if [[ $# -eq 0 ]]; then
    usage
    exit 2
fi

for agent in "$@"; do
    if ! is_agent "$agent"; then
        echo "error: unknown agent: $agent" >&2
        usage
        exit 2
    fi
done

status=0
for agent in "$@"; do
    if ! "$action" "$agent"; then
        status=1
    fi
done
exit "$status"
