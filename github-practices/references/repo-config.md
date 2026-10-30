# Remote repo configuration

## Index

- [Before touching anything](#before-touching-anything)
- [Default branch](#default-branch)
- [Merge methods](#merge-methods)
- [Labels](#labels)
- [Rulesets](#rulesets)
- [Secret scanning and Dependabot](#secret-scanning-and-dependabot)

Every remote change is applied with one command and undone with another. Ask for an OK before running them: they are not reversible through git.

## Before touching anything

```bash
REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)
SKILL="<skill-dir>"
gh auth status
gh api "repos/$REPO" --jq '{default_branch, allow_squash_merge, allow_merge_commit, allow_rebase_merge, delete_branch_on_merge, squash_merge_commit_title, squash_merge_commit_message}'
# The merge methods undo reads these variables.
SQUASH=$(gh api "repos/$REPO" --jq .allow_squash_merge)
MERGE=$(gh api "repos/$REPO" --jq .allow_merge_commit)
REBASE=$(gh api "repos/$REPO" --jq .allow_rebase_merge)
SQUASH_TITLE=$(gh api "repos/$REPO" --jq .squash_merge_commit_title)
SQUASH_MESSAGE=$(gh api "repos/$REPO" --jq .squash_merge_commit_message)
gh api "repos/$REPO" --jq '.security_and_analysis | {secret_scanning: .secret_scanning.status, push_protection: .secret_scanning_push_protection.status}'
# The security undo reads these two variables; without them it would turn off what was already on.
SCAN_STATE=$(gh api "repos/$REPO" --jq '.security_and_analysis.secret_scanning.status // "unknown"')
PUSH_PROTECTION_STATE=$(gh api "repos/$REPO" --jq '.security_and_analysis.secret_scanning_push_protection.status // "unknown"')
gh api "repos/$REPO/vulnerability-alerts" --silent && VULN_ALERTS=on || VULN_ALERTS=off
AUTOFIX=$(gh api "repos/$REPO/automated-security-fixes" --jq 'if .enabled then "on" else "off" end' 2>/dev/null || echo unknown)
echo "vulnerability-alerts=$VULN_ALERTS automated-security-fixes=$AUTOFIX"
```

`SKILL` is `<skill-dir>`, the directory that holds this skill's `SKILL.md`: replace it with the same path `SKILL.md` uses to run the audit.

Keep the output of the snapshot commands above: it is the state you return to if something goes wrong. You need admin permission; `gh api repos/$REPO --jq '.permissions.admin'` confirms it.

Order: first the default branch, then the merge methods, then labels and finally rulesets. A ruleset on `~DEFAULT_BRANCH` applies to whatever default exists at that moment.

## Default branch

TBD:

```bash
gh repo edit "$REPO" --default-branch main
```

Gitflow:

```bash
gh repo edit "$REPO" --default-branch develop
```

Undo: repeat with the previous name. The branch must exist on the remote and cannot be the only one. Changing the default deletes nothing.

## Merge methods

The "Before touching anything" snapshot stores `allow_squash_merge`, `allow_merge_commit`, `allow_rebase_merge`, `squash_merge_commit_title` and `squash_merge_commit_message`. Those values are what the undo restores, not the GitHub defaults.

TBD, squash only:

```bash
gh repo edit "$REPO" \
  --enable-squash-merge \
  --squash-merge-commit-message pr-title \
  --enable-merge-commit=false \
  --enable-rebase-merge=false
```

Gitflow, squash and merge commit:

```bash
gh repo edit "$REPO" \
  --enable-squash-merge \
  --enable-merge-commit \
  --squash-merge-commit-message pr-title \
  --enable-rebase-merge=false
```

`pr-title` uses the PR title as the squash message, which is what release-please needs to read.

Undo, restoring the snapshot:

```bash
gh api -X PATCH "repos/$REPO" \
  -F allow_squash_merge="$SQUASH" \
  -F allow_merge_commit="$MERGE" \
  -F allow_rebase_merge="$REBASE" \
  -f squash_merge_commit_title="$SQUASH_TITLE" \
  -f squash_merge_commit_message="$SQUASH_MESSAGE"
```

The variables come from the snapshot at the top of this file. `-F` converts booleans to the right type; with `-f` they would travel as strings.

### Delete the branch on merge

It is a separate setting: it needs its own OK and is undone separately.

```bash
gh repo edit "$REPO" --delete-branch-on-merge
```

Undo:

```bash
gh repo edit "$REPO" --delete-branch-on-merge=false
```

## Labels

Create only the missing ones. Do not use `--force`: it would overwrite the color and description of labels that already existed.

```bash
gh label list --repo "$REPO" --limit 200 --json name -q '.[].name' > /tmp/labels-before.txt
: > /tmp/labels-created.txt
jq -r '.[] | [.name, .color, .description] | @tsv' "$SKILL/assets/labels.json" |
while IFS=$'\t' read -r name color description; do
  if ! grep -Fqx "$name" /tmp/labels-before.txt; then
    gh label create "$name" --repo "$REPO" --color "$color" --description "$description"
    echo "$name" >> /tmp/labels-created.txt
  fi
done
```

Before running it, show the exact list of missing ones. Ask for an OK per label, or a single one for that list if the person prefers.

Undo: delete only the ones created in this session, never the pre-existing ones.

```bash
while read -r name; do gh label delete "$name" --repo "$REPO" --yes; done < /tmp/labels-created.txt
```

## Rulesets

Apply the one for the model, only one of the two:

```bash
gh api -X POST "repos/$REPO/rulesets" --input "$SKILL/assets/rulesets/tbd.json"
gh api -X POST "repos/$REPO/rulesets" --input "$SKILL/assets/rulesets/gitflow.json"
```

List them to get the id:

```bash
gh api "repos/$REPO/rulesets" --jq '.[] | "\(.id) \(.name)"'
```

Undo:

```bash
gh api -X DELETE "repos/$REPO/rulesets/<id>"
```

Modifying requires sending the full body:

```bash
gh api -X PUT "repos/$REPO/rulesets/<id>" --input "$SKILL/assets/rulesets/tbd.json"
```

The rulesets include `deletion`, `non_fast_forward`, `pull_request` with zero approvals (valid for single-person repos) and `required_linear_history` only in TBD. They do not include status checks because the names depend on each CI; add them by hand once the workflow exists.

In Gitflow the ruleset covers `develop` and `main` with the same merge methods, because `main` needs a merge commit. That leaves the merge commit into `develop` open; if you want to close it, apply a second ruleset to `develop` with `allowed_merge_methods: ["squash"]`. Without it, squash into `develop` is a team convention.

If you want to require CODEOWNERS review, enable `require_code_owner_review` in the ruleset and add `.github/CODEOWNERS` based on `assets/CODEOWNERS.example`. With a single maintainer it adds nothing.

On private repos, rulesets require GitHub Pro, Team or Enterprise. If the API returns 403, declare it and continue: it is not a repo failure.

## Secret scanning and Dependabot

Secret scanning and push protection:

```bash
gh repo edit "$REPO" --enable-secret-scanning --enable-secret-scanning-push-protection
```

Undo, restoring the snapshot and without turning off what was already on:

```bash
[[ "$SCAN_STATE" == "disabled" ]] && gh repo edit "$REPO" --enable-secret-scanning=false
[[ "$PUSH_PROTECTION_STATE" == "disabled" ]] && gh repo edit "$REPO" --enable-secret-scanning-push-protection=false
```

On public repos it is free. On private ones it requires GitHub Advanced Security; if it is not available, the command fails and that is declared.

Dependabot alerts and automated fixes:

```bash
gh api -X PUT "repos/$REPO/vulnerability-alerts"
gh api -X PUT "repos/$REPO/automated-security-fixes"
```

Undo, restoring the snapshot:

```bash
[[ "$VULN_ALERTS" == "off" ]] && gh api -X DELETE "repos/$REPO/vulnerability-alerts"
[[ "$AUTOFIX" == "off" ]] && gh api -X DELETE "repos/$REPO/automated-security-fixes"
```

If the snapshot had them on, the undo does not touch them. Turning them off would delete the alert state.

Version updates are enabled with `.github/dependabot.yml` in the repo (copy `assets/.github/dependabot.yml`), not with a remote command. That change goes in a PR.
