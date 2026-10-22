# github-practices

[![CI](https://github.com/iDiagoValeta/github-practices/actions/workflows/ci.yml/badge.svg)](https://github.com/iDiagoValeta/github-practices/actions/workflows/ci.yml) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A Claude Code skill (also for OpenCode and other AI agents) that audits a GitHub repository against best practices and applies only the changes you approve. It is for anyone who maintains a repo and wants branch protection, templates, labels and releases set up right without reading every GitHub doc: install it, run `/github-practices` and review the report.

## What it checks

It covers the branching model, branch names, issues and pull requests, Conventional Commits, labels, rulesets, CODEOWNERS, Dependabot and release-please. It does not impose a model: it picks one from the repo and explains why.

- **Branching model.** Detects trunk-based development or Gitflow from the branches and the default branch, and recommends one with its reasons.
- **Branch protection.** Rulesets on the default branch: pull request required, required status checks, no force push, no deletion and linear history in trunk-based development.
- **Pull requests.** Template, median size (250 lines is the target, 500 the warning) and linked issue through a closing keyword.
- **Branch names.** `<prefix>/<ISSUE>-<context>` (only `automated/`, `internal/` and `revert/` may skip the issue), checked against the repo name and the 63 character limit.
- **Issues.** Bug and feature forms that prelabel `kind/bug` and `kind/feature`.
- **Labels.** The ten labels the skill expects, from `kind/*` to `breaking` and `skip-release`.
- **Commits.** Conventional Commits in the last 50 non-merge commits and the optional `.gitmessage` template.
- **Merge methods.** Squash only in trunk-based development, merge commits allowed in Gitflow.
- **CODEOWNERS.** Suggested when the repo has more than one contributor.
- **Security.** Dependabot, secret scanning and push protection.
- **Releases.** release-please for the version and the CHANGELOG.
- **Flow metrics.** Linked issue, PR size, time from open to merge and branch names in the report, with thresholds for review time, lead time and deployment frequency in `references/metrics.md`.

Every finding carries a severity (high, medium, low or info). When something cannot be checked (token permissions, plan limits or a history too short to measure), the audit reports it as its own info finding.

## Quick start

In Claude Code 2.1.275 or later:

```text
/plugin install github-practices --marketplace iDiagoValeta/github-practices
```

In OpenCode:

```bash
npx skills add iDiagoValeta/github-practices -a opencode
```

Or clone and run `./install.sh`:

```bash
git clone https://github.com/iDiagoValeta/github-practices.git
cd github-practices
./install.sh
```

Then run `/github-practices:github-practices` if you installed the plugin, or `/github-practices` if you used `npx skills`, `gh skill` or `install.sh`.

## Example

Real output of `python3 github-practices/scripts/audit.py --path . --repo iDiagoValeta/github-practices` run on this repo, trimmed and with the local path anonymised:

```text
# GitHub practices audit

- Repo: `iDiagoValeta/github-practices`
- Path: `/path/to/github-practices`
- Default branch: `main`

## Branching model

- Current: **tbd**
- Recommended: **tbd**
- Reason: 1 contributor(s), 0 tag(s) and no release branches: short branches and squash are enough

...

### High (2)

- **[high] pr.template-missing** (pull requests): There is no PR template, so the description does not remind Closes #N or the scope of the task.
  - Fix: Create .github/pull_request_template.md with a linked issue section, what changes and how it was tested.
- **[high] protection.ruleset-missing** (protection): No active ruleset covers: main.
  - Fix: Create a ruleset on the default branch with PR, checks, no force push and no deletion.

...
```

## Install

### Claude Code (plugin)

One step on Claude Code 2.1.275 or later:

```text
/plugin install github-practices --marketplace iDiagoValeta/github-practices
```

Two steps on any version with plugins:

```bash
claude plugin marketplace add iDiagoValeta/github-practices
claude plugin install github-practices@github-practices
```

The marketplace is the repo itself, so there is nothing else to host. As a plugin the skill is invoked as `/github-practices:github-practices`; installed with `install.sh` or `gh skill` it is `/github-practices`.

To remove the plugin and its marketplace entry:

```bash
claude plugin marketplace remove github-practices
```

It also uninstalls the plugins it provided and deletes their saved options and data.

### OpenCode and other agents

The skills CLI (vercel-labs/skills) installs the skill where the agent reads it:

```bash
npx skills add iDiagoValeta/github-practices -a opencode
```

`pnpm dlx skills add iDiagoValeta/github-practices -a opencode` does the same. Project scope installs into `.agents/skills/github-practices/`, which OpenCode reads.

A recent GitHub CLI with the skill command in preview installs it for any of 40+ agents, Claude Code and OpenCode included:

```bash
gh skill install iDiagoValeta/github-practices github-practices --agent opencode --scope user
```

Use `--agent claude-code` for Claude Code.

### Manual

Clone the repo and run the installer:

```bash
git clone https://github.com/iDiagoValeta/github-practices.git
cd github-practices
./install.sh
```

It creates the symlink `~/.claude/skills/github-practices` pointing to `github-practices/` in this repo. It is idempotent: if it already exists and points here, it does nothing; if something else exists at that path, it aborts without deleting it.

OpenCode also reads `~/.claude/skills/`, so the same command works there.

#### Per project

Copy the skill into the repo where you want to use it:

```bash
mkdir -p .claude/skills
cp -r /path/to/github-practices/github-practices .claude/skills/
```

That way it is versioned with the project and available only there.

#### Uninstall

```bash
./install.sh --uninstall
```

It removes the symlink only if it points to this repo. If it points elsewhere, or the path holds a real directory or file, it aborts without touching it.

## Usage

In Claude Code or OpenCode:

```text
/github-practices
```

Installed as a plugin, the same skill is `/github-practices:github-practices`.

Or ask in natural language: "audit this repo", "protect main", "does this branch follow the convention?", "set up the issue and PR templates".

The flow is always the same: audit in read-only mode, present the report by severity, recommend the branching model with its reasons, apply only what is approved and re-audit. Files go on an `internal/github-practices-setup` branch with a draft PR; every remote change needs an explicit OK, showing the command and how to undo it.

## Approval gate

Saying "protect main" is a request, not an approval. The agent shows the exact command and its undo, then waits for an answer. Instructions alone were not enough for some models, so the repo ships permission blocks that turn the first GitHub write into a prompt:

- OpenCode: merge `github-practices/assets/agent-permissions/opencode.json` into the project `opencode.json` or into `~/.config/opencode/opencode.json`.
- Claude Code: merge `github-practices/assets/agent-permissions/claude-settings.json` into `.claude/settings.json`.

The block allows everything except the commands listed here: `gh api` with an explicit method, `gh repo edit`, label create and delete, PR merge and `git push`. In a non-interactive run the agent then stops at the first write instead of applying it.

## Structure

```text
.
├── .claude-plugin/                 Claude Code plugin and marketplace manifests
├── github-practices/
│   ├── SKILL.md                    Entry point: flow, safety and file map
│   ├── references/
│   │   ├── branching.md            Branching model, default branch, names, merge, hotfix
│   │   ├── pull-requests.md        Lifecycle, anatomy, size, scope
│   │   ├── commits-and-release.md  Conventional Commits, signing, release-please
│   │   ├── repo-config.md          Rulesets, default branch, merge methods, labels
│   │   └── metrics.md              Flow metrics and thresholds
│   ├── scripts/
│   │   ├── audit.py                Read-only audit with gh
│   │   └── branch_name.py          Validates a branch name against the repo
│   └── assets/
│       ├── .github/                Issue and PR templates, Dependabot, release-please
│       ├── rulesets/               Rulesets for TBD and Gitflow
│       ├── agent-permissions/      Permission gates for OpenCode and Claude Code
│       ├── CODEOWNERS.example
│       ├── labels.json
│       ├── release-please-config.json
│       ├── .release-please-manifest.json
│       └── .gitmessage
├── evals/
│   └── evals.json                  Three scenarios for discovery and behaviour
├── tests/
│   ├── test_audit.py               Audit rules over temporary trees
│   ├── test_branch_name.py         Branch name rules and limits
│   ├── test_install.py             Installer and safe uninstall
│   └── test_skill_format.py        Frontmatter, size, links and forbidden characters
├── .github/workflows/ci.yml        Python 3.12 tests and install.sh syntax
├── install.sh                      Symlink installer and safe uninstaller
├── LICENSE
└── README.md
```

## Tests

```bash
python3 -m unittest discover -s tests -v
bash -n install.sh
```

The tests validate the audit and branch-name scripts, the format of `SKILL.md` (frontmatter, size, links and forbidden characters) and the uninstaller in temporary directories; `bash -n install.sh` checks the installer syntax. CI runs both on Python 3.12.

## Requirements

- Claude Code for the plugin install, or Node.js with `npx` for the skills CLI.
- Python 3, standard library only. CI tests on Python 3.12.
- `gh` CLI authenticated (`gh auth status`) for `audit.py`. Without it the audit exits 2 and says why.
- `git`, to read the local templates and the last commits.
- `bash` for `install.sh`.
- Read access to the GitHub API. The audit only reads; it changes nothing.

## License

MIT. See [LICENSE](LICENSE).
