---
name: github-practices
description: Audits a GitHub repository against good practices for branching (trunk-based or Gitflow), pull requests, issues, rulesets, CODEOWNERS, conventional commits, labels and releases, and applies only the changes the user approves. Use when asked to audit or configure a repo, choose a branching model, validate a branch name, protect the main branch, prepare issue and PR templates, configure Dependabot or set up release-please.
license: MIT
metadata:
  opencode/slash: "true"
---

# github-practices

Audits a repo and applies only what is approved. It does not impose a branching model: it picks one from the repo and explains why.

**Mandatory gate before any write to GitHub** (`gh api -X POST|PUT|PATCH|DELETE`, `gh repo edit`, `gh label create|delete`, push, PR): the request must carry a written OK for THAT specific change (for example "apply the ruleset"). A blanket OK ("I approve all the changes") covers only the change types the request names or that you already showed with their undo. Asking for the goal ("I want to protect main") is NOT that OK. Without it, your reply ends with the command, its undo and the question "shall I apply it?", even if nobody is there to answer. For agents that support permission rules, the block in `assets/agent-permissions/` enforces the same gate.

## When to use it

- Asked to audit, tidy or configure a GitHub repository.
- A choice between trunk-based (TBD) and Gitflow is needed, or the default branch must be reviewed.
- A branch must be named, a PR drafted, an issue linked or a change labelled.
- `main` must be protected, or Dependabot, secret scanning or release-please enabled.
- The repo flow must be measured (linked issue, PR size, time to merge).

## Flow

Copyable checklist:

```markdown
- [ ] Audit the repo in read-only mode
- [ ] Present the report by severity (high, medium, low)
- [ ] Choose the branching model and explain why
- [ ] Apply only what is approved, change by change
- [ ] Re-audit and confirm the gap is closed
```

### 1. Audit

Run the audit script, do not read it:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/audit.py" --repo owner/name --path . --prs 30
```

In Claude Code the path is `${CLAUDE_SKILL_DIR}/scripts/audit.py`. In other agents, use the path of the directory where this skill is installed. `--json` prints JSON to stdout (redirect it to a file if you want to keep it). The audit is read-only: it changes nothing on GitHub.

If the repo has no templates, workflows or rulesets, do not treat it as an error: that is the normal starting point and the report must say so.

### 2. Report

Sort the findings by severity and give the recommended model with its reasons.

- **High**: it breaks the flow or the protection (missing ruleset on the default branch, missing PR template, PR median above 500 lines).
- **Medium**: a piece is missing or inconsistent (merge methods, labels, Dependabot, issue forms, CODEOWNERS with several maintainers, release-please, Conventional Commits, linked issue, orphan `develop`).
- **Low**: form only (`.gitmessage`).
- **Info**: not enough data to conclude.

Also state what could not be checked: insufficient permissions, rulesets unavailable on a private repo (403), history without enough PRs.

### 3. Choose the branching model

When in doubt, TBD:

- **TBD** (`main` only, short branches, squash): personal or single-person repos, services with continuous deployment, any case without grouped versions.
- **Gitflow** (`main` and `develop` as default): planned releases grouping several features, several collaborators, old versions still maintained.

If the repo already uses a model and there is no clear contradiction, respect it. The default branch must match the model. Details in [references/branching.md](references/branching.md).

### 4. Apply only what is approved

Separate two kinds of change, because they carry different risk.

**Repo files** (templates, workflows, versioned configuration):

1. Create the branch `internal/github-practices-setup` from the default branch.
2. Copy only the assets that cover the approved findings, keeping their path: `assets/.github/...` goes to `.github/...`.
3. A single draft PR, with the report and what was applied in the description. If the agent opened it, the person who asked for the change merges it; the skill never merges.
4. If the repo has `CONTRIBUTING.md` and it contradicts this flow, `CONTRIBUTING.md` wins: adapt and say so in the report.

**Remote configuration** (rulesets, default branch, merge methods, labels, Dependabot):

- Ask for an explicit OK for each change, after showing the exact command and the command that undoes it.
- Do not group several changes into one confirmation unless the request itself pre-approves them by name: each one touches GitHub and each one is reverted separately.
- If a change fails halfway, stop and report the real state; do not chain the next one.
- The commands and their rollback are in [references/repo-config.md](references/repo-config.md).

### 5. Re-audit

Run `audit.py` again and compare with the initial report. A change is done when it disappears from the report, not when the command returns zero. Anything that depends on traffic or time (flow metrics) is declared pending. The ruleset asset does not include status checks on purpose, because their names depend on each CI: `protection.status-checks` stays low until stable checks exist.

## Safety rules

- Nothing remote without an explicit OK per change, showing the command and how to undo it.
- Asking for the change ("protect main") is not the OK: it is the request. Show the command and wait for the answer.
- If you cannot ask (non-interactive run) and the OK is not written in the request, apply nothing: hand over the commands and stop.
- No force push, no deleting other people's branches, no history rewriting.
- Files always go on the `internal/github-practices-setup` branch with a draft PR, never straight to the default branch.
- On a contradiction between this skill and `CONTRIBUTING.md`, the repo wins.
- If the API returns 403 for lack of plan, declare it and continue; do not treat it as a repo failure.

## Where things are

References (read only the one you need):

| File | When to read it |
|---|---|
| [references/branching.md](references/branching.md) | Choose TBD or Gitflow, set the default branch, name branches, decide squash or merge commit, hotfix and baselines |
| [references/pull-requests.md](references/pull-requests.md) | Open or review a PR, size, scope, template |
| [references/commits-and-release.md](references/commits-and-release.md) | Conventional Commits, signing, `breaking` and `skip-release` labels, release-please |
| [references/repo-config.md](references/repo-config.md) | Remote changes: default branch, merge methods, labels, rulesets, Dependabot and secret scanning |
| [references/metrics.md](references/metrics.md) | Read the flow report and its thresholds without turning them into a judgement |

Scripts (run them, do not read them):

| File | What for |
|---|---|
| [scripts/audit.py](scripts/audit.py) | Read-only audit with `--repo`, `--path`, `--prs`, `--json` |
| [scripts/branch_name.py](scripts/branch_name.py) | Validate `branch repo` against prefix, issue and length |

Assets (copy, do not edit):

| File | What to copy |
|---|---|
| [assets/rulesets/tbd.json](assets/rulesets/tbd.json) | Ruleset for the default branch in TBD |
| [assets/rulesets/gitflow.json](assets/rulesets/gitflow.json) | Ruleset for `main` and `develop` in Gitflow |
| [assets/.github/pull_request_template.md](assets/.github/pull_request_template.md) | PR template |
| [assets/.github/ISSUE_TEMPLATE/bug.yml](assets/.github/ISSUE_TEMPLATE/bug.yml) | Bug issue form with `kind/bug` |
| [assets/.github/ISSUE_TEMPLATE/feature.yml](assets/.github/ISSUE_TEMPLATE/feature.yml) | Feature issue form with `kind/feature` |
| [assets/.github/ISSUE_TEMPLATE/config.yml](assets/.github/ISSUE_TEMPLATE/config.yml) | Disables blank issues |
| [assets/labels.json](assets/labels.json) | Labels `kind/*`, `breaking`, `skip-release` |
| [assets/CODEOWNERS.example](assets/CODEOWNERS.example) | CODEOWNERS if there is more than one maintainer |
| [assets/.gitmessage](assets/.gitmessage) | Commit template with Why and How |
| [assets/release-please-config.json](assets/release-please-config.json) | release-please configuration |
| [assets/.release-please-manifest.json](assets/.release-please-manifest.json) | Initial version manifest |
| [assets/.github/workflows/release-please.yml](assets/.github/workflows/release-please.yml) | release-please workflow |
| [assets/.github/dependabot.yml](assets/.github/dependabot.yml) | Dependabot version updates |
| [assets/agent-permissions/](assets/agent-permissions/) | Permission block that stops the agent at the first GitHub write |
