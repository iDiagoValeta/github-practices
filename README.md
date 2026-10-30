# github-practices

[![CI](https://github.com/iDiagoValeta/github-practices/actions/workflows/ci.yml/badge.svg)](https://github.com/iDiagoValeta/github-practices/actions/workflows/ci.yml) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

An agent skill for AI coding agents that audits a GitHub repository against best practices and applies only the changes you approve. It works in Claude Code, Codex, Cursor, Gemini CLI, GitHub Copilot, OpenCode, Windsurf, ZCode and any agent that reads the open [SKILL.md format](https://agentskills.io). It is for anyone who maintains a repo and wants branch protection, templates, labels and releases set up right without reading every GitHub doc: install it, ask your agent to audit the repo and review the report.

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

Install with the skills CLI, naming your agent:

```bash
npx skills add iDiagoValeta/github-practices -a <agent>
```

Or with the GitHub CLI, which needs a recent `gh` with the skill command in preview:

```bash
gh skill install iDiagoValeta/github-practices github-practices --agent <agent> --scope user
```

`gh skill` supports every listed agent except Windsurf and ZCode, which use the skills CLI or `install.sh`.

`<agent>` is one of `claude-code`, `codex`, `cursor`, `gemini-cli`, `github-copilot`, `opencode`, `windsurf` or `zcode`. See [Install](#install) for the install options for each agent, the manual symlink and how to invoke the skill.

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

Every agent reads the same `github-practices/` folder and the same `SKILL.md`; only the skills directory and the install command change. The table summarises the paths; the sections below give the commands for each agent, alphabetically.

| Agent | `--agent` value | User dir | Project dir | How to invoke |
|---|---|---|---|---|
| Claude Code | `claude-code` | `~/.claude/skills` | `.claude/skills` | `/github-practices`, or `/github-practices:github-practices` as a plugin |
| Codex | `codex` | `~/.agents/skills` | `.agents/skills` | `$github-practices`, or `/skills` to pick it |
| Cursor | `cursor` | `~/.cursor/skills` | `.cursor/skills` or `.agents/skills` | type `/` in the Agent chat and pick `github-practices` |
| Gemini CLI | `gemini-cli` | `~/.gemini/skills` | `.gemini/skills` or `.agents/skills` | activated from the description; `/skills list` shows it |
| GitHub Copilot | `github-copilot` | `~/.copilot/skills` | `.github/skills`, `.claude/skills` or `.agents/skills` | loaded automatically when relevant |
| OpenCode | `opencode` | `~/.config/opencode/skills` | `.opencode/skills`, `.claude/skills` or `.agents/skills` | `/github-practices` |
| Windsurf | `windsurf` | `~/.codeium/windsurf/skills` | `.windsurf/skills` or `.agents/skills` | `/github-practices` |
| ZCode | `zcode` | `~/.zcode/skills` | `.zcode/skills` | ask in natural language |

Codex installs into the shared `~/.agents/skills`, which Cursor, Gemini CLI, GitHub Copilot, OpenCode and Windsurf also read. `pnpm dlx skills add` does the same as `npx skills add`; without `-g` the skills CLI installs into the project, and `-g` selects the user scope.

### Claude Code

Native plugin, one step on Claude Code 2.1.275 or later:

```text
/plugin install github-practices --marketplace iDiagoValeta/github-practices
```

Two steps on any version with plugins:

```bash
claude plugin marketplace add iDiagoValeta/github-practices
claude plugin install github-practices@github-practices
```

The marketplace is the repo itself, so there is nothing else to host. To remove the plugin and its marketplace entry:

```bash
claude plugin marketplace remove github-practices
```

It also uninstalls the plugins it provided and deletes their saved options and data.

Skills CLI:

```bash
npx skills add iDiagoValeta/github-practices -a claude-code
```

GitHub CLI:

```bash
gh skill install iDiagoValeta/github-practices github-practices --agent claude-code --scope user
```

Manual:

```bash
./install.sh claude-code
```

It creates the symlink `~/.claude/skills/github-practices`. For one project, copy `github-practices/` into `.claude/skills/`.

Invoke it as `/github-practices`, or as `/github-practices:github-practices` when installed as a plugin.

### Codex

Skills CLI:

```bash
npx skills add iDiagoValeta/github-practices -a codex
```

GitHub CLI:

```bash
gh skill install iDiagoValeta/github-practices github-practices --agent codex --scope user
```

Manual:

```bash
./install.sh codex
```

Codex reads the shared `~/.agents/skills`, so the link lives there. For one project, copy `github-practices/` into `.agents/skills/`.

Invoke it as `$github-practices`, or run `/skills` and pick it from the list.

### Cursor

Skills CLI:

```bash
npx skills add iDiagoValeta/github-practices -a cursor
```

GitHub CLI:

```bash
gh skill install iDiagoValeta/github-practices github-practices --agent cursor --scope user
```

Manual:

```bash
./install.sh cursor
```

It creates the symlink `~/.cursor/skills/github-practices`. For one project, copy `github-practices/` into `.cursor/skills/` or `.agents/skills/`.

Invoke it by typing `/` in the Agent chat and picking `github-practices`.

### Gemini CLI

Native installer:

```bash
gemini skills install https://github.com/iDiagoValeta/github-practices.git --consent
```

Add `--scope workspace` for the project. It finds the skill in the repo subfolder on its own.

Skills CLI:

```bash
npx skills add iDiagoValeta/github-practices -a gemini-cli
```

GitHub CLI:

```bash
gh skill install iDiagoValeta/github-practices github-practices --agent gemini-cli --scope user
```

Manual:

```bash
./install.sh gemini-cli
```

It creates the symlink `~/.gemini/skills/github-practices`. For one project, copy `github-practices/` into `.gemini/skills/` or `.agents/skills/`.

Gemini CLI activates it from the description when the request matches; `/skills list` shows it.

### GitHub Copilot

Skills CLI:

```bash
npx skills add iDiagoValeta/github-practices -a github-copilot
```

GitHub CLI:

```bash
gh skill install iDiagoValeta/github-practices github-practices --agent github-copilot --scope user
```

Manual:

```bash
./install.sh github-copilot
```

It creates the symlink `~/.copilot/skills/github-practices`. For one project, copy `github-practices/` into `.github/skills/`, `.claude/skills/` or `.agents/skills/`.

GitHub Copilot loads it automatically when relevant.

### OpenCode

Skills CLI:

```bash
npx skills add iDiagoValeta/github-practices -a opencode
```

GitHub CLI:

```bash
gh skill install iDiagoValeta/github-practices github-practices --agent opencode --scope user
```

Manual:

```bash
./install.sh opencode
```

It creates the symlink `~/.config/opencode/skills/github-practices`. For one project, copy `github-practices/` into `.opencode/skills/`, `.claude/skills/` or `.agents/skills/`.

OpenCode also reads `~/.claude/skills/` and `~/.agents/skills/`. Invoke it as `/github-practices`.

### Windsurf

Skills CLI:

```bash
npx skills add iDiagoValeta/github-practices -a windsurf
```

`gh skill` does not support Windsurf; use the skills CLI or the manual install.

Manual:

```bash
./install.sh windsurf
```

It creates the symlink `~/.codeium/windsurf/skills/github-practices`. For one project, copy `github-practices/` into `.windsurf/skills/` or `.agents/skills/`.

Invoke it as `/github-practices`.

### ZCode

Skills CLI:

```bash
npx skills add iDiagoValeta/github-practices -a zcode
```

`gh skill` does not support ZCode; use the skills CLI or the manual install.

Manual:

```bash
./install.sh zcode
```

It creates the symlink `~/.zcode/skills/github-practices`. For one project, copy `github-practices/` into `.zcode/skills/`.

Ask ZCode in natural language, for example "audit this repo".

### Any other agent

Any agent that reads the open SKILL.md format works the same way: copy the `github-practices/` folder into the skills directory your agent documents.

```bash
git clone https://github.com/iDiagoValeta/github-practices.git
cp -r github-practices/github-practices <agent-skills-dir>/
```

### install.sh

From a clone of this repo:

```bash
git clone https://github.com/iDiagoValeta/github-practices.git
cd github-practices
./install.sh AGENT...
./install.sh --uninstall AGENT...
./install.sh --list
```

`AGENT` is one of `claude-code`, `codex`, `cursor`, `gemini-cli`, `github-copilot`, `opencode`, `windsurf` or `zcode`. It creates a symlink to `github-practices/` in this repo at the user directory of the agent; `codex` targets the shared `~/.agents/skills`. `--list` prints every agent with the path it uses.

It is idempotent: if the link already exists and points here, it does nothing; if something else exists at that path, it aborts without deleting it. Several agents in one call are all processed, and the exit status is 1 if any failed. No arguments or an unknown agent print the usage on stderr and exit 2.

Uninstall removes the symlink only if it points to this repo. If it points elsewhere, or the path holds a real directory or file, it aborts without touching it:

```bash
./install.sh --uninstall claude-code
```

## Usage

Invoke the skill the way your agent does, as the table above says, or ask in natural language: "audit this repo", "protect main", "does this branch follow the convention?", "set up the issue and PR templates".

The flow is always the same: audit in read-only mode, present the report by severity, recommend the branching model with its reasons, apply only what is approved and re-audit. Files go on an `internal/github-practices-setup` branch with a draft PR; every remote change needs an explicit OK, showing the command and how to undo it.

## Approval gate

Saying "protect main" is a request, not an approval. The agent shows the exact command and its undo, then waits for an answer. Instructions alone were not enough for some models, so Claude Code and OpenCode ship permission blocks that turn the first GitHub write into a prompt:

- Claude Code: merge `github-practices/assets/agent-permissions/claude-settings.json` into `.claude/settings.json`.
- OpenCode: merge `github-practices/assets/agent-permissions/opencode.json` into the project `opencode.json` or into `~/.config/opencode/opencode.json`.

The block allows everything except the commands listed here: `gh api` with an explicit method, `gh repo edit`, label create and delete, PR merge and `git push`. In a non-interactive run the agent then stops at the first write instead of applying it. Other agents rely only on the gate written in `SKILL.md`, which is the weaker of the two: check that your agent asks before the first remote change.

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
├── install.sh                      Symlink installer for every agent and safe uninstaller
├── LICENSE
└── README.md
```

## Tests

```bash
python3 -m unittest discover -s tests -v
bash -n install.sh
```

The tests validate the audit and branch-name scripts, the format of `SKILL.md` (frontmatter, size, links and forbidden characters) and the installer and uninstaller in temporary directories; `bash -n install.sh` checks the installer syntax. CI runs both on Python 3.12.

## Requirements

- An agent that supports Agent Skills, such as any of the agents above.
- Node.js 22.20 or later with `npx` for the skills CLI, or the GitHub CLI with the skill command in preview for `gh skill`.
- Python 3, standard library only. CI tests on Python 3.12.
- `gh` CLI authenticated (`gh auth status`) for `audit.py`. Without it the audit exits 2 and says why.
- `git`, to read the local templates and the last commits.
- `bash` for `install.sh`.
- Read access to the GitHub API. The audit only reads; it changes nothing.

## License

MIT. See [LICENSE](LICENSE).
