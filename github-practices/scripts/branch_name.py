#!/usr/bin/env python3
"""Validate branch names against rule 2 of the spec.

Pure `check_branch` function so the audit can reuse it without invoking the
process again, and a minimal CLI to use it by hand or from the skill.

Usage: branch_name.py <branch> <repo>
Exits 0 if the branch is valid, 1 if there are problems (printed to stdout).
"""

import re
import sys

PREFIXES = {
    "bugfix",
    "dependency",
    "deprecation",
    "documentation",
    "feature",
    "hotfix",
    "improvement",
    "internal",
    "refactoring",
    "release",
    "removal",
    "revert",
    "security",
    "automated",
}

# Issue like GH-12 or project key like ABC-123. Uppercase is required because
# the spec fixes that format and mixing gh-12/ABC-123 breaks traceability.
ISSUE_RE = re.compile(r"^([A-Z][A-Z0-9]*-\d+)(?:-(.+))?$")
CHARACTERS_RE = re.compile(r"^[A-Za-z0-9-]+$")
NO_ISSUE_PREFIXES = {"automated", "internal", "revert"}
MAX_LENGTH = 63


def check_branch(branch, repo_name):
    """Return the list of problems with `branch`; empty if it is valid.

    `repo_name` may come as owner/repo: only the final name counts, which is
    what GitHub uses when concatenating for the 63 limit.
    """
    problems = []
    if not branch:
        return ["the branch is empty"]

    if "/" not in branch:
        return [
            "missing prefix: the format is <prefix>/<ISSUE>-<context> "
            "with prefix in " + ", ".join(sorted(PREFIXES))
        ]

    prefix, rest = branch.split("/", 1)
    if prefix not in PREFIXES:
        problems.append(
            "prefix '%s' not allowed; valid ones: %s"
            % (prefix, ", ".join(sorted(PREFIXES)))
        )
    if not rest:
        problems.append("missing the name after the prefix")
        return problems

    if not rest[0].isalpha():
        problems.append("after the prefix it must start with a letter, not '%s'" % rest[0])
    if not CHARACTERS_RE.match(rest):
        problems.append("only [A-Za-z0-9-] is allowed in the branch name")

    if prefix not in NO_ISSUE_PREFIXES:
        match = ISSUE_RE.match(rest)
        if not match:
            problems.append(
                "missing the issue with format GH-<n> or KEY-<n> at the start "
                "(only automated/, internal/ and revert/ may go without an issue)"
            )
        elif match.group(2) is None:
            problems.append("missing the context after the issue")

    repo_base = repo_name.rsplit("/", 1)[-1]
    length = len(repo_base) + 1 + len(rest)
    if length > MAX_LENGTH:
        problems.append(
            "name too long: %d characters counting the repo, maximum %d"
            % (length, MAX_LENGTH)
        )

    return problems


def main(argv):
    if len(argv) != 3:
        print("usage: branch_name.py <branch> <repo>", file=sys.stderr)
        return 2
    problems = check_branch(argv[1], argv[2])
    if not problems:
        return 0
    for problem in problems:
        print("%s: %s" % (argv[1], problem))
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
