#!/usr/bin/env python3
"""Read-only audit of a repository against the spec.

Deliberate split: `collect_*` talks to `gh` and the file system; everything
else is pure functions over dicts. That way the rules can be tested without
a network and the skill does not depend on the model improvising.

Usage:
    audit.py [--repo owner/name] [--path .] [--prs 30] [--json]

Exits 0 if the audit completes (even with findings), 2 if `gh` is missing or
not authenticated, and 1 if the repo cannot be determined or read.
"""

import argparse
import json
import re
import shutil
import statistics
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from branch_name import check_branch

REQUIRED_LABELS = [
    "kind/feature",
    "kind/bug",
    "kind/improvement",
    "kind/refactoring",
    "kind/documentation",
    "kind/dependency",
    "kind/internal",
    "kind/security",
    "breaking",
    "skip-release",
]

RELEASE_PREFIXES = ("release/",)

# GitHub rules required by the spec, with their real type in the rulesets API.
PROTECTION_RULES = {
    "pull_request": ("protection.pull-request", "high", "PR required"),
    "required_status_checks": ("protection.status-checks", "low", "required checks"),
    "non_fast_forward": ("protection.force-push", "medium", "no force push"),
    "deletion": ("protection.deletion", "medium", "no branch deletion"),
    "required_linear_history": ("protection.linear-history", "medium", "linear history"),
}

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}

CONVENTIONAL_RE = re.compile(
    r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)"
    r"(\([^)]+\))?!?: .+"
)

# Loose reference in the title or the branch. It links nothing: it is used to
# warn about a mention that ends up without a close, not to count the PR as
# linked.
ISSUE_IN_TEXT_RE = re.compile(r"(#[0-9]+|\b[A-Z][A-Z0-9]*-\d+\b)")

# GitHub only closes an issue with a keyword and a number or URL in the body.
CLOSING_RE = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b\s*:?\s*"
    r"(?:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#\d+"
    r"|https?://github\.com/[^/\s]+/[^/\s]+/issues/\d+"
    r"|#\d+)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Collection (impure): everything that leaves the process lives here.
# ---------------------------------------------------------------------------


def _run(cmd, cwd=None):
    """Run without a shell and without a TTY: nothing here may ask for input."""
    try:
        process = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, check=False
        )
    except FileNotFoundError:
        return 127, "", "executable not found: %s" % cmd[0]
    return process.returncode, process.stdout, process.stderr


def _gh_json(args, cwd=None):
    code, output, error = _run(["gh", *args], cwd=cwd)
    if code != 0:
        return None, error.strip() or "gh exited with code %d" % code
    try:
        return json.loads(output), None
    except json.JSONDecodeError as exc:
        return None, "gh response is not JSON: %s" % exc


def _gh_lines(args, cwd=None):
    """For paginated listings: ask for `.[].field` and split by lines."""
    code, output, error = _run(["gh", *args], cwd=cwd)
    if code != 0:
        return None, error.strip() or "gh exited with code %d" % code
    return [line for line in output.splitlines() if line.strip()], None


def collect_repo(owner_repo):
    data, error = _gh_json(["api", "repos/" + owner_repo])
    return data, error


def collect_rulesets(owner_repo):
    """Return the rulesets or mark them as unverifiable.

    On plans without rulesets the API answers 403/404. That is not an audit
    failure: it is declared and the audit continues, as the spec requires.
    """
    data, error = _gh_json(["api", "repos/%s/rulesets" % owner_repo])
    if data is None:
        return {"status": "unavailable", "rulesets": [], "detail": error}
    rulesets = []
    for summary in data:
        ruleset = summary
        # The listing may come without `rules`; the detail does bring them.
        if "rules" not in ruleset and ruleset.get("id") is not None:
            detail, _ = _gh_json(
                ["api", "repos/%s/rulesets/%s" % (owner_repo, ruleset["id"])]
            )
            if detail is not None:
                ruleset = detail
        rulesets.append(ruleset)
    return {"status": "ok", "rulesets": rulesets}


def collect_branches(owner_repo):
    names, _ = _gh_lines(
        ["api", "repos/%s/branches" % owner_repo, "--paginate", "-q", ".[].name"]
    )
    return names


def collect_labels(owner_repo):
    names, _ = _gh_lines(
        ["api", "repos/%s/labels" % owner_repo, "--paginate", "-q", ".[].name"]
    )
    return names


def collect_tags(owner_repo):
    # One page is enough for the heuristic; there is no need to walk the history.
    names, _ = _gh_lines(
        ["api", "repos/%s/tags?per_page=100" % owner_repo, "-q", ".[].name"]
    )
    return names


def collect_contributors(owner_repo):
    # Paginated on purpose: the API page size is 100 and counting only the
    # first page would falsify the heuristic on large repos.
    logins, _ = _gh_lines(
        [
            "api",
            "repos/%s/contributors" % owner_repo,
            "--paginate",
            "-q",
            ".[].login",
        ]
    )
    if logins is None:
        return None
    return len(logins)


def collect_prs(owner_repo, limit):
    """Approximate the latest N merged PRs.

    `gh pr list` sorts by creation date, not merge date. A margin of 3N is
    requested and the result is sorted by `mergedAt`; a very old PR merged
    late can fall outside the window, which is documented as an approximation.
    """
    fields = (
        "number,title,body,headRefName,additions,deletions,"
        "createdAt,mergedAt,isDraft,closingIssuesReferences"
    )
    data, _ = _gh_json(
        [
            "pr",
            "list",
            "--repo",
            owner_repo,
            "--state",
            "merged",
            "--limit",
            str(limit * 3),
            "--json",
            fields,
        ]
    )
    if data is None:
        return None
    return sorted(data, key=lambda pr: pr.get("mergedAt") or "", reverse=True)[:limit]


def _find_file(directory, name):
    """Case-insensitive search: GitHub accepts both variants."""
    if not directory.is_dir():
        return None
    for entry in sorted(directory.iterdir()):
        if entry.is_file() and entry.name.lower() == name.lower():
            return entry
    return None


def _find_directory(directory, name):
    if not directory.is_dir():
        return None
    for entry in sorted(directory.iterdir()):
        if entry.is_dir() and entry.name.lower() == name.lower():
            return entry
    return None


def _pr_template(base):
    for directory in (base / ".github", base, base / "docs"):
        found = _find_file(directory, "pull_request_template.md")
        if found is not None:
            return str(found.relative_to(base))
    # Variant with several templates: .github/PULL_REQUEST_TEMPLATE/*.md
    folder = _find_directory(base / ".github", "PULL_REQUEST_TEMPLATE")
    if folder is not None and any(
        child.is_file() and child.suffix.lower() == ".md" for child in folder.iterdir()
    ):
        return str(folder.relative_to(base))
    return None


def _template_labels(text):
    """Extract `labels:` from a YAML file or from a md template frontmatter."""
    labels = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = re.match(r"^\s*labels:\s*(.*)$", line)
        if not match:
            continue
        rest = match.group(1).strip()
        if rest:
            for part in re.split(r"[,\s]+", rest.strip("[]")):
                part = part.strip("'\"")
                if part:
                    labels.append(part)
        else:
            # YAML block form:
            # labels:
            #   - kind/bug
            for following in lines[index + 1 :]:
                item = re.match(r"^\s+-\s*(.+?)\s*$", following)
                if not item:
                    break
                labels.append(item.group(1).strip("'\""))
    return labels


def _issue_templates(base):
    directory = base / ".github" / "ISSUE_TEMPLATE"
    if not directory.is_dir():
        return []
    templates = []
    for entry in sorted(directory.iterdir()):
        if not entry.is_file() or entry.suffix.lower() not in (".yml", ".yaml", ".md"):
            continue
        # config.yml configures the chooser; it is not an issue form.
        if entry.name.lower() in ("config.yml", "config.yaml"):
            continue
        text = entry.read_text(encoding="utf-8", errors="ignore")
        templates.append(
            {"name": entry.name, "labels": _template_labels(text)}
        )
    return templates


def _has_release_please(base):
    workflows = base / ".github" / "workflows"
    if not workflows.is_dir():
        return False
    for entry in sorted(workflows.iterdir()):
        if entry.suffix.lower() not in (".yml", ".yaml") or not entry.is_file():
            continue
        text = entry.read_text(encoding="utf-8", errors="ignore").lower()
        if "release-please" in text:
            return True
    return False


def collect_local(path):
    base = Path(path).expanduser().resolve()
    code, _, _ = _run(["git", "-C", str(base), "rev-parse", "--git-dir"])
    subjects = []
    if code == 0:
        # Without --no-merges, Gitflow "Merge ..." commits lower the
        # Conventional Commits percentage by following the recommendation itself.
        _, output, _ = _run(
            ["git", "-C", str(base), "log", "-n", "50", "--no-merges", "--format=%s"]
        )
        subjects = [line for line in output.splitlines() if line.strip()]
    return {
        "is_git_repo": code == 0,
        "pr_template": _pr_template(base),
        "issue_templates": _issue_templates(base),
        "codeowners": any(
            _find_file(directory, "CODEOWNERS") is not None
            for directory in (base / ".github", base, base / "docs")
        ),
        "dependabot": any(
            _find_file(base / ".github", name) is not None
            for name in ("dependabot.yml", "dependabot.yaml")
        ),
        "release_please": _has_release_please(base),
        "gitmessage": (base / ".gitmessage").is_file(),
        "commit_subjects": subjects,
    }


def collect_state(owner_repo, path, pr_limit, include_local=True):
    repo, _ = collect_repo(owner_repo)
    return {
        "repo": repo,
        "branches": collect_branches(owner_repo),
        "labels": collect_labels(owner_repo),
        "prs": collect_prs(owner_repo, pr_limit),
        "rulesets": collect_rulesets(owner_repo),
        "contributors": collect_contributors(owner_repo),
        "tags": collect_tags(owner_repo),
        # None means "not checked", not "does not exist": local checks are
        # skipped when --path is not a clone of the --repo repo.
        "local": collect_local(path) if include_local else None,
    }


# ---------------------------------------------------------------------------
# Evaluation (pure): input dicts, output findings.
# ---------------------------------------------------------------------------


def _finding(identifier, area, severity, message, fix):
    return {
        "id": identifier,
        "area": area,
        "severity": severity,
        "message": message,
        "fix": fix,
    }


def detect_model(branches, default_branch):
    """Gitflow only if `develop` exists and is the default; otherwise TBD.

    It detects what the repo does, not what its documentation says.
    """
    if default_branch == "develop" and "develop" in (branches or ["develop"]):
        return "gitflow"
    return "tbd"


def recommend_model(current, state):
    """Spec heuristic: contributors, tags and release branches.

    It respects the current model unless there is a clear contradiction: a
    Gitflow with a single person, no tags and no release branches is
    maintenance without use.
    """
    branches = state.get("branches")
    contributors = state.get("contributors")
    tags = state.get("tags")

    # An API failure is not a zero. Without that data the model is not moved:
    # the current one is kept and what is missing is declared.
    if branches is None or contributors is None or tags is None:
        missing = [
            name
            for name, value in (
                ("branches", branches),
                ("contributors", contributors),
                ("tags", tags),
            )
            if value is None
        ]
        return current, [
            "insufficient data: not verifiable (%s); keeping %s."
            % (", ".join(missing), current)
        ]

    releases = [branch for branch in branches if branch.startswith(RELEASE_PREFIXES)]

    if current == "gitflow":
        if contributors <= 1 and len(tags) < 3 and not releases:
            return "tbd", [
                "Gitflow with %d contributor(s), %d tag(s) and no release branches: "
                "there are no versions to group" % (contributors, len(tags))
            ]
        return "gitflow", [
            "The repo already uses Gitflow (%d contributor(s), %d tag(s), %d release branch(es))"
            % (contributors, len(tags), len(releases))
        ]

    if releases and contributors >= 2:
        return "gitflow", [
            "%d release branch(es) and %d contributor(s): there are versions to group"
            % (len(releases), contributors)
        ]
    if contributors >= 3 and len(tags) >= 3:
        return "gitflow", [
            "%d contributor(s) and %d tag(s): planned releases and several "
            "collaborators" % (contributors, len(tags))
        ]
    return "tbd", [
        "%d contributor(s), %d tag(s) and no release branches: short branches and "
        "squash are enough" % (contributors, len(tags))
    ]


def _check_model(state):
    findings = []
    branches = state.get("branches") or []
    default = (state.get("repo") or {}).get("default_branch") or ""
    current = detect_model(branches, default)
    recommended, reasons = recommend_model(current, state)

    if "develop" in branches and default != "develop":
        findings.append(
            _finding(
                "branch.develop-unused",
                "branches",
                "medium",
                "The develop branch exists but the default is '%s'; the repo "
                "operates as TBD with an orphan develop branch."
                % (default or "unknown"),
                "Delete develop if it does not group releases, or make it the "
                "default if the team really maintains Gitflow.",
            )
        )

    if recommended != current:
        message = "Current model %s; the heuristic recommends %s: %s." % (
            current,
            recommended,
            "; ".join(reasons),
        )
    else:
        message = "Current model %s, consistent with the heuristic: %s." % (
            current,
            "; ".join(reasons),
        )

    # It is a recommendation, not a defect: the spec forbids imposing the model.
    findings.append(
        _finding(
            "branch.model",
            "branches",
            "info",
            message,
            "If the model changes, move the default branch and the merge "
            "methods in the same step so the repo is not left half done.",
        )
    )
    return findings


def _check_labels(state):
    labels = state.get("labels")
    if labels is None:
        return [
            _finding(
                "labels.unverifiable",
                "labels",
                "info",
                "The repo label list could not be read.",
                "Check the gh token permissions and run the audit again.",
            )
        ]
    present = {label.lower() for label in labels}
    missing = [label for label in REQUIRED_LABELS if label.lower() not in present]
    if not missing:
        return []
    return [
        _finding(
            "labels.missing",
            "labels",
            "medium",
            "Missing labels from the spec: %s." % ", ".join(missing),
            "Create them with: gh label create <name> --repo <owner/repo> "
            "(for example: %s)." % missing[0],
        )
    ]


def _check_pr_template(state):
    if state.get("local", {}).get("pr_template"):
        return []
    return [
        _finding(
            "pr.template-missing",
            "pull requests",
            "high",
            "There is no PR template, so the description does not remind Closes #N "
            "or the scope of the task.",
            "Create .github/pull_request_template.md with a linked issue section, "
            "what changes and how it was tested.",
        )
    ]


def _check_issue_templates(state):
    templates = state.get("local", {}).get("issue_templates") or []
    if not templates:
        return [
            _finding(
                "issues.forms-missing",
                "issues",
                "medium",
                "There are no templates in .github/ISSUE_TEMPLATE/.",
                "Add issue forms for bug and feature that prelabel "
                "kind/bug and kind/feature.",
            )
        ]

    names = " ".join(template.get("name", "").lower() for template in templates)
    labels = {
        label.lower()
        for template in templates
        for label in template.get("labels", [])
    }
    problems = []
    if "bug" not in names:
        problems.append("missing the bug form")
    if "feature" not in names:
        problems.append("missing the feature form")
    if "kind/bug" not in labels:
        problems.append("no form prelabels kind/bug")
    if "kind/feature" not in labels:
        problems.append("no form prelabels kind/feature")
    if not problems:
        return []
    return [
        _finding(
            "issues.forms-incomplete",
            "issues",
            "medium",
            "Incomplete issue templates: %s." % "; ".join(problems),
            "Complete .github/ISSUE_TEMPLATE/ with one form per type and "
            "labels: [kind/bug] or labels: [kind/feature].",
        )
    ]


def _check_local_files(state):
    local = state.get("local") or {}
    contributors = state.get("contributors")
    findings = []

    if not local.get("dependabot"):
        findings.append(
            _finding(
                "dependabot.missing",
                "security",
                "medium",
                "There is no .github/dependabot.yml: dependencies do not receive "
                "automatic updates.",
                "Add .github/dependabot.yml with version updates for the repo "
                "ecosystems.",
            )
        )

    if not local.get("release_please"):
        findings.append(
            _finding(
                "release.release-please-missing",
                "release",
                "medium",
                "No workflow uses release-please, so the version and the CHANGELOG "
                "are maintained by hand.",
                "Add .github/workflows/release-please.yml with the "
                "googleapis/release-please-action action.",
            )
        )

    if not local.get("codeowners"):
        if contributors is None:
            findings.append(
                _finding(
                    "codeowners.missing",
                    "protection",
                    "info",
                    "There is no CODEOWNERS and the number of contributors could "
                    "not be read: not verifiable whether it is needed.",
                    "Check the token permissions or review Settings > "
                    "Collaborators before deciding.",
                )
            )
        elif contributors > 1:
            findings.append(
                _finding(
                    "codeowners.missing",
                    "protection",
                    "medium",
                    "There are %d contributors and no CODEOWNERS: reviews are not "
                    "assigned automatically." % contributors,
                    "Add .github/CODEOWNERS with at least the critical paths.",
                )
            )

    if not local.get("gitmessage"):
        findings.append(
            _finding(
                "commits.gitmessage-missing",
                "commits",
                "low",
                "There is no .gitmessage with the Why/How template (it is optional).",
                "Optional: create .gitmessage and enable it with "
                "git config commit.template .gitmessage.",
            )
        )

    return findings


def _check_commits(state):
    local = state.get("local", {})
    if not local.get("is_git_repo"):
        return [
            _finding(
                "commits.unverifiable",
                "commits",
                "info",
                "The path is not a git repository: commits cannot be read.",
                "Run with --path pointing to the repository clone.",
            )
        ]
    subjects = local.get("commit_subjects") or []
    if not subjects:
        return [
            _finding(
                "commits.conventional",
                "commits",
                "info",
                "There are no local commits to evaluate.",
                "Check that the clone has history (git fetch).",
            )
        ]
    conventional = sum(1 for subject in subjects if CONVENTIONAL_RE.match(subject))
    percentage = round(100.0 * conventional / len(subjects), 1)
    if percentage >= 90:
        return []
    return [
        _finding(
            "commits.conventional",
            "commits",
            "medium",
            "Only %s%% of the last %d commits follow Conventional Commits."
            % (_format_number(percentage), len(subjects)),
            "Rewriting history is not worth it: apply the convention from "
            "now on and use it as the base for release-please.",
        )
    ]


def _check_merge(state, model):
    repo = state.get("repo") or {}
    keys = ("allow_squash_merge", "allow_merge_commit", "allow_rebase_merge")
    if not all(key in repo for key in keys):
        return []
    problems = []
    if not repo.get("allow_squash_merge"):
        problems.append("squash disabled")
    if model == "tbd":
        if repo.get("allow_merge_commit"):
            problems.append("merge commit allowed (TBD requires squash only)")
        if repo.get("allow_rebase_merge"):
            problems.append("rebase allowed (TBD requires squash only)")
    else:
        if not repo.get("allow_merge_commit"):
            problems.append(
                "merge commit disabled (Gitflow needs it for develop->main)"
            )
        if repo.get("allow_rebase_merge"):
            problems.append("rebase allowed")
    if not problems:
        return []
    merge_commit = "true" if model == "gitflow" else "false"
    return [
        _finding(
            "merge.settings",
            "merge",
            "medium",
            "Merge methods inconsistent with %s: %s."
            % (model.upper(), "; ".join(problems)),
            "Adjust in Settings > General > Pull requests, or with "
            "gh api -X PATCH repos/<owner/repo> -F allow_squash_merge=true "
            "-F allow_merge_commit=%s -F allow_rebase_merge=false." % merge_commit,
        )
    ]


def _ruleset_targets(ruleset, branch):
    conditions = (ruleset.get("conditions") or {}).get("ref_name") or {}
    include = conditions.get("include") or []
    exclude = conditions.get("exclude") or []
    references = {branch, "refs/heads/" + branch}
    if any(reference in exclude for reference in references):
        return False
    return bool(
        references & set(include) or "~DEFAULT_BRANCH" in include or "~ALL" in include
    )


def _check_protection(state, model):
    rulesets = state.get("rulesets") or {}
    if rulesets.get("status") != "ok":
        detail = rulesets.get("detail") or "no detail"
        return [
            _finding(
                "protection.unverifiable",
                "protection",
                "info",
                "Rulesets not verifiable with this token or plan (%s)." % detail,
                "Review Settings > Rules manually; private repos need "
                "GitHub Pro/Team.",
            )
        ]

    default = (state.get("repo") or {}).get("default_branch") or ""
    target = [default] if default else []
    if model == "gitflow":
        target += [branch for branch in ("main", "develop") if branch not in target]
    active = [
        ruleset
        for ruleset in rulesets.get("rulesets") or []
        if ruleset.get("enforcement", "active") == "active"
    ]

    missing_coverage = [
        branch for branch in target if not any(_ruleset_targets(rs, branch) for rs in active)
    ]
    if missing_coverage or not target:
        return [
            _finding(
                "protection.ruleset-missing",
                "protection",
                "high",
                "No active ruleset covers: %s."
                % (", ".join(missing_coverage) or "the default branch"),
                "Create a ruleset on the default branch with PR, checks, no "
                "force push and no deletion.",
            )
        ]

    # Coverage is checked per branch: a `main` ruleset does not protect
    # `develop`. Only what each target branch covers is aggregated.
    rules_per_branch = {
        branch: _rule_types(active, branch) for branch in target
    }

    required = ["pull_request", "required_status_checks", "non_fast_forward", "deletion"]
    if model == "tbd":
        required.append("required_linear_history")

    findings = []
    for rule_type in required:
        missing = [branch for branch in target if rule_type not in rules_per_branch[branch]]
        if not missing:
            continue
        identifier, severity, description = PROTECTION_RULES[rule_type]
        if rule_type == "required_status_checks":
            message = (
                "Branches %s do not require status checks; add them once there is "
                "CI with stable names." % ", ".join(missing)
            )
        else:
            message = "Branches %s do not include the '%s' rule (%s)." % (
                ", ".join(missing),
                rule_type,
                description,
            )
        findings.append(
            _finding(
                identifier,
                "protection",
                severity,
                message,
                "Add the rule to the ruleset of each target branch from "
                "Settings > Rules, or with the rulesets API.",
            )
        )
    return findings


def _rule_types(active, branch):
    """Rule types that really apply to `branch`.

    A `required_status_checks` without configured checks blocks nothing, so it
    is not counted as a present rule.
    """
    types = set()
    for ruleset in active:
        if not _ruleset_targets(ruleset, branch):
            continue
        for rule in ruleset.get("rules") or []:
            rule_type = rule.get("type")
            if not rule_type:
                continue
            if rule_type == "required_status_checks":
                parameters = rule.get("parameters") or {}
                if not parameters.get("required_status_checks"):
                    continue
            types.add(rule_type)
    return types


def _check_security(state):
    analysis = (state.get("repo") or {}).get("security_and_analysis")
    if analysis is None:
        return [
            _finding(
                "security.unverifiable",
                "security",
                "info",
                "The API does not return security_and_analysis for this repo.",
                "Check secret scanning and push protection in Settings > "
                "Code security.",
            )
        ]
    findings = []
    pairs = [
        ("secret_scanning", "security.secret-scanning", "secret scanning"),
        (
            "secret_scanning_push_protection",
            "security.push-protection",
            "push protection",
        ),
    ]
    for key, identifier, name in pairs:
        # If the key is missing, the feature is not available on this plan or
        # this repo type: it cannot be stated that it is off.
        data = analysis.get(key)
        if not data or data.get("status") != "disabled":
            continue
        findings.append(
            _finding(
                identifier,
                "security",
                "medium",
                "%s is disabled." % name,
                "Enable %s in Settings > Code security if the plan allows it." % name,
            )
        )
    return findings


def _pr_linked(pr):
    """Real link: a closing reference in the API or a keyword in the body."""
    if pr.get("closingIssuesReferences"):
        return True
    return bool(CLOSING_RE.search(pr.get("body") or ""))


def _pr_mentioned(pr):
    """Loose mention in the title or the branch: links nor closes nothing."""
    text = "%s %s" % (pr.get("title") or "", pr.get("headRefName") or "")
    return bool(ISSUE_IN_TEXT_RE.search(text))


def _hours_to_merge(pr):
    created = pr.get("createdAt")
    merged = pr.get("mergedAt")
    if not created or not merged:
        return None
    try:
        start = _parse_date(created)
        end = _parse_date(merged)
    except ValueError:
        return None
    return (end - start).total_seconds() / 3600.0


def _parse_date(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _format_number(value):
    """Format 50.0 as '50' without losing 50.5; avoids noise in messages."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def compute_metrics(state):
    prs = state.get("prs")
    if prs is None:
        return {"prs_total": None}
    total = len(prs)
    if total == 0:
        return {
            "prs_total": 0,
            "issue_link_pct": None,
            "median_size": None,
            "median_hours": None,
            "branch_names_pct": None,
            "draft_pct": None,
            "draft_detectable": False,
        }
    repo_name = ((state.get("repo") or {}).get("nameWithOwner") or "").split("/")[-1]
    linked = sum(1 for pr in prs if _pr_linked(pr))
    sizes = [
        (pr.get("additions") or 0) + (pr.get("deletions") or 0) for pr in prs
    ]
    hours = [value for value in (_hours_to_merge(pr) for pr in prs) if value is not None]
    valid = sum(1 for pr in prs if not check_branch(pr.get("headRefName") or "", repo_name))
    return {
        "prs_total": total,
        "issue_link_pct": round(100.0 * linked / total, 1),
        "median_size": statistics.median(sizes),
        "median_hours": round(statistics.median(hours), 1) if hours else None,
        "branch_names_pct": round(100.0 * valid / total, 1),
        # isDraft on an already merged PR is always false: whether it went
        # through draft cannot be known, so the metric is not invented.
        "draft_pct": None,
        "draft_detectable": False,
    }


def _check_metrics(state):
    prs = state.get("prs")
    if prs is None:
        return [
            _finding(
                "prs.unverifiable",
                "pull requests",
                "info",
                "The merged PRs could not be read.",
                "Check gh permissions and the --prs limit.",
            )
        ]
    if not prs:
        return [
            _finding(
                "prs.empty",
                "pull requests",
                "info",
                "There are no merged PRs in the queried range; no data for "
                "the metrics.",
                "Retry with a higher --prs once there is history.",
            )
        ]

    metrics = compute_metrics(state)
    findings = []
    repo_name = ((state.get("repo") or {}).get("nameWithOwner") or "").split("/")[-1]

    if metrics["issue_link_pct"] < 90:
        findings.append(
            _finding(
                "prs.issue-link",
                "pull requests",
                "medium",
                "Only %s%% of merged PRs have a linked issue "
                "(target >=90%%)."
                % _format_number(metrics["issue_link_pct"]),
                "Require `Closes #N` in the body (closing keyword) and "
                "remind it in the PR template.",
            )
        )

    mentions = [
        pr
        for pr in prs
        if not _pr_linked(pr) and _pr_mentioned(pr)
    ]
    if mentions:
        examples = ", ".join(
            "#%s" % pr.get("number") for pr in mentions[:3] if pr.get("number")
        )
        findings.append(
            _finding(
                "prs.issue-mention",
                "pull requests",
                "info",
                "Mention without a link in %d PR(s): the issue appears in the title "
                "or the branch, but no closing keyword links it%s."
                % (len(mentions), (" (%s)" % examples) if examples else ""),
                "Add `Closes #N` to the PR body; a mention in the title or in "
                "the branch does not close the issue.",
            )
        )

    size = metrics["median_size"]
    if size > 500:
        severity = "high"
    elif size > 250:
        severity = "medium"
    else:
        severity = None
    if severity:
        findings.append(
            _finding(
                "prs.size",
                "pull requests",
                severity,
                "The median PR size is %s lines (ideal <=250, warning >500)."
                % _format_number(size),
                "Split the work into single-concern PRs; the practical limit "
                "is 250 lines.",
            )
        )

    if metrics["branch_names_pct"] < 90:
        invalid = [
            pr.get("headRefName") or ""
            for pr in prs
            if check_branch(pr.get("headRefName") or "", repo_name)
        ]
        examples = ", ".join(invalid[:3])
        findings.append(
            _finding(
                "prs.branch-names",
                "branches",
                "medium",
                "Only %s%% of PR branches follow <prefix>/<ISSUE>-<context> "
                "(examples: %s)." % (_format_number(metrics["branch_names_pct"]), examples),
                "Use scripts/branch_name.py when creating the branch and fix the "
                "names before opening the PR.",
            )
        )

    return findings


def evaluate(state):
    """All findings, sorted by severity and then by id."""
    model = detect_model(
        state.get("branches") or [],
        (state.get("repo") or {}).get("default_branch") or "",
    )
    findings = []
    findings += _check_model(state)
    findings += _check_labels(state)
    if state.get("local") is None:
        findings.append(
            _finding(
                "local.no-verificado",
                "local review",
                "info",
                "Local files and commits were not checked: %s"
                % (
                    state.get("local_reason")
                    or "the local path does not match the given repo"
                ),
                "Run with --path pointing to a clone of the repo or without --repo "
                "to infer it from the remote.",
            )
        )
    else:
        findings += _check_pr_template(state)
        findings += _check_issue_templates(state)
        findings += _check_local_files(state)
        findings += _check_commits(state)
    findings += _check_merge(state, model)
    findings += _check_protection(state, model)
    findings += _check_security(state)
    findings += _check_metrics(state)
    return sorted(findings, key=lambda f: (SEVERITY_ORDER[f["severity"]], f["id"]))


# ---------------------------------------------------------------------------
# Presentation
# ---------------------------------------------------------------------------


def build_report(owner_repo, path, state):
    default = (state.get("repo") or {}).get("default_branch") or ""
    current = detect_model(state.get("branches") or [], default)
    recommended, reasons = recommend_model(current, state)
    return {
        "repo": owner_repo,
        "path": str(path),
        "default_branch": default,
        "model": {
            "current": current,
            "recommended": recommended,
            "reasons": reasons,
        },
        "findings": evaluate(state),
        "metrics": compute_metrics(state),
    }


def render_markdown(report):
    lines = [
        "# GitHub practices audit",
        "",
        "- Repo: `%s`" % report["repo"],
        "- Path: `%s`" % report["path"],
        "- Default branch: `%s`" % (report.get("default_branch") or "unknown"),
        "",
        "## Branching model",
        "",
        "- Current: **%s**" % report["model"]["current"],
        "- Recommended: **%s**" % report["model"]["recommended"],
    ]
    lines += ["- Reason: %s" % reason for reason in report["model"]["reasons"]]
    lines += ["", "## Findings", ""]

    by_severity = {severity: [] for severity in SEVERITY_ORDER}
    for finding in report["findings"]:
        by_severity[finding["severity"]].append(finding)

    if not report["findings"]:
        lines.append("No findings.")
    for severity in SEVERITY_ORDER:
        group = by_severity[severity]
        if not group:
            continue
        lines.append("### %s (%d)" % (severity.capitalize(), len(group)))
        lines.append("")
        for finding in group:
            lines.append(
                "- **[%s] %s** (%s): %s"
                % (
                    finding["severity"],
                    finding["id"],
                    finding["area"],
                    finding["message"],
                )
            )
            lines.append("  - Fix: %s" % finding["fix"])
        lines.append("")

    metrics = report["metrics"]
    lines += ["## Metrics", ""]
    if metrics.get("prs_total") is None:
        lines.append("Not computable: the PR history could not be read.")
    elif metrics.get("prs_total") == 0:
        lines.append("There are no merged PRs in the queried range.")
    else:
        lines += [
            "| Metric | Value | Target |",
            "| --- | --- | --- |",
            "| Merged PRs analyzed | %s | |" % metrics["prs_total"],
            "| PRs with linked issue | %s%% | >=90%% |"
            % _format_number(metrics["issue_link_pct"]),
            "| Median size (lines) | %s | <=250 |"
            % _format_number(metrics["median_size"]),
            "| Hours from open to merge (median) | %s | DORA reference |"
            % (
                _format_number(metrics["median_hours"])
                if metrics.get("median_hours") is not None
                else "not computable"
            ),
            "| PR branches with a valid name | %s%% | >=90%% |"
            % _format_number(metrics["branch_names_pct"]),
            "| PRs that went through draft | not detectable | |",
        ]
    lines += [
        "",
        "Metrics and thresholds are a reference, not a judgement of the team.",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _gh_ready():
    if shutil.which("gh") is None:
        return False, "the gh executable was not found"
    code, _, error = _run(["gh", "auth", "status"])
    if code != 0:
        return False, "gh is not authenticated: %s" % (error.strip() or "no detail")
    return True, ""


def _current_repo(path):
    code, output, _ = _run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
        cwd=path,
    )
    if code != 0:
        return None
    return output.strip() or None


def _remote_origin(path):
    code, output, _ = _run(
        [
            "git",
            "-C",
            str(Path(path).expanduser().resolve()),
            "remote",
            "get-url",
            "origin",
        ]
    )
    if code != 0:
        return None
    return output.strip() or None


def _normalize_repo(value):
    """Reduce owner/name and its https and ssh forms to lowercase `owner/name`."""
    if not value:
        return None
    text = value.strip().rstrip("/")
    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", text):
        return text.lower()
    for prefix in (
        "https://github.com/",
        "http://github.com/",
        "ssh://git@github.com/",
        "git@github.com:",
        "git://github.com/",
    ):
        if text.startswith(prefix):
            rest = text[len(prefix):]
            break
    else:
        return None
    if rest.endswith(".git"):
        rest = rest[:-4]
    parts = [part for part in rest.split("/") if part]
    if len(parts) != 2:
        return None
    return ("%s/%s" % (parts[0], parts[1])).lower()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Audit a repo against the github-practices spec (read-only)."
    )
    parser.add_argument(
        "--repo", help="owner/name; if missing it is inferred from the --path remote"
    )
    parser.add_argument(
        "--path",
        default=None,
        help="local clone of the repo; its files and commits are audited",
    )
    parser.add_argument("--prs", type=int, default=30, help="merged PRs to analyze")
    parser.add_argument("--json", action="store_true", help="dump the report as JSON")
    args = parser.parse_args(argv)

    ready, reason = _gh_ready()
    if not ready:
        print("error: %s" % reason, file=sys.stderr)
        return 2

    path = args.path or "."
    repo = args.repo or _current_repo(path)
    if not repo:
        print(
            "error: the repo could not be inferred; pass --repo owner/name or run "
            "inside a clone with a GitHub remote",
            file=sys.stderr,
        )
        return 1

    # With --repo and --path at the same time, local checks are only valid if
    # the clone is of the given repo; if not, they are skipped and the reason is given.
    include_local = True
    local_reason = None
    if args.repo and args.path is not None:
        remote = _remote_origin(path)
        if _normalize_repo(remote) != _normalize_repo(args.repo):
            include_local = False
            local_reason = (
                "the origin remote of %s is %s, not %s"
                % (path, remote or "unknown", args.repo)
            )

    state = collect_state(repo, path, args.prs, include_local=include_local)
    if local_reason:
        state["local_reason"] = local_reason
    if state["repo"] is None:
        print(
            "error: %s could not be read with gh api; check permissions and name"
            % repo,
            file=sys.stderr,
        )
        return 1

    report = build_report(repo, Path(path).expanduser().resolve(), state)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
