# Branches

## Choose a model

Two models, one per repo. The model drives the default branch, the merge methods and the ruleset; if they do not fit together, the repo is misconfigured.

| Signal | TBD | Gitflow |
|---|---|---|
| Personal or single-person repo | yes | no |
| Service with continuous deployment | yes | no |
| Several features must ship together in one release | no | yes |
| Several people maintaining old versions | no | yes |
| The repo already uses a model and there is no contradiction | respected | respected |

TBD (trunk based): `main` is the only long branch. Each change lives on a short branch, hours or a few days, and lands with squash. There is no `develop`.

Gitflow: `main` is what is deployed, `develop` is the default branch and the integration branch, `release/*` freezes a version and `hotfix/*` comes out of `main`. Add maintenance branches only if there are old versions to sustain.

When in doubt, TBD. Gitflow is paid for with sync merges and grouped releases; if you do not group versions, you do not need it.

## Default branch

| Model | Default |
|---|---|
| TBD | `main` |
| Gitflow | `develop`, with `main` as the production branch |

If the repo already uses another name, rename it before applying rulesets: a ruleset on `~DEFAULT_BRANCH` silently moves to another branch if you change the default later.

## Names

```
<prefix>/<ISSUE>-<context>
```

Examples: `feature/GH-12-login-sso`, `bugfix/ABC-345-null-token`, `internal/github-practices-setup`.

| Prefix | When |
|---|---|
| `feature` | New functionality |
| `bugfix` | Bug in development |
| `hotfix` | Bug in production, comes out of `main` |
| `improvement` | Improvement to something existing without new functionality |
| `refactoring` | Internal change without a behaviour change |
| `documentation` | Documentation only |
| `dependency` | Dependency bump or change |
| `deprecation` | Marking something as obsolete |
| `removal` | Removing functionality |
| `revert` | Undoing a previous change |
| `security` | Security patch |
| `internal` | CI, tooling and repo configuration |
| `automated` | Bots: Dependabot, release-please, syncs |
| `release` | Preparing a release, Gitflow only |

Name rules:

- The issue is `GH-<n>` or an external key such as `ABC-123`.
- After the prefix the name starts with a letter and uses only `[A-Za-z0-9-]`.
- `len(repo_name + "-" + branch_without_prefix) <= 63`. Several tools prefix the branch with the repo name; past that limit, some truncate and the link breaks.
- `internal/`, `revert/` and `automated/` may go without an issue.
- Lowercase except for the issue key.

## Merge strategy

| Source | Target | TBD | Gitflow |
|---|---|---|---|
| `feature/*`, `bugfix/*`, `improvement/*`, `refactoring/*`, `documentation/*`, `dependency/*`, `security/*`, `internal/*` | integration | squash to `main` | squash to `develop` |
| `automated/*` | integration | squash to `main` | merge commit `--no-ff` |
| `hotfix/*` | production | squash to `main` | squash to `main` |
| `release/*` | production | does not exist | merge commit `--no-ff` to `main` |
| `develop` | `main` | does not exist | merge commit `--no-ff` |
| `main` | `develop` | does not exist | merge commit from `automated/sync-main` |
| `main-x.x` | maintenance | does not exist | cherry-pick from `main` or its own fix with squash |

Squash leaves one commit per PR, with the PR title as the message. That is why the title must be Conventional Commits: release-please reads it.

Configure the allowed merge methods of the repo in line with the table. In TBD leave squash only; in Gitflow leave squash and merge commit, never rebase.

## Hotfix

1. Issue with the incident.
2. `hotfix/GH-<n>-<context>` from `main`.
3. PR to `main`, squash, deploy.
4. In Gitflow, bring the fix back to `develop`: cherry-pick or an `automated/sync-main` branch with a merge commit. Do not merge `develop` into `main` to "recover" changes halfway through a hotfix.

## Baselines `main-x.x`

Open a `main-1.x` branch when `main` has already moved to another major or minor and the previous one still has to be sustained. It is not the default branch and carries the same ruleset as production.

- Add `refs/heads/main-*` to the ruleset `include`.
- Fixes come out of `bugfix/GH-<n>-<context>` against the baseline and land with squash.
- Propagate the fix to `main` with cherry-pick; if it does not apply, do not force it.
- Tags on that line follow the version it maintains, for example `1.4.3`.
- release-please can release from a baseline with `target-branch` and its own configuration, but do not set it up if nobody maintains that line.
