# Pull requests

## Lifecycle

1. **Draft early.** Open the PR when you start, not when you finish. The draft reserves the number, links the issue and shows the scope.
2. **Ready when it is ready for review.** CI green, full description and no test commits. Asking for review before that wastes the reviewer's time.
3. **Review.** Resolve the threads, do not close them without an answer. A requested change is either discussed or applied.
4. **Whoever opened the PR merges it**, not the reviewer. If an agent opened it, the person who asked for the change merges it; the skill never merges. Whoever merges checks that the checks are still green and decides the moment. The reviewer approves; they do not merge someone else's work.

A PR is not left open just in case: if it is not going to land, close it and reopen it when it is due.

## Anatomy

| Field | Rule |
|---|---|
| Title | `<type>(<scope>): <summary> (GH-<n>)`, the same format as the final commit |
| Description | What changes and why; `Closes #<n>` to close the issue |
| Target | TBD: `main`. Gitflow: `develop`; `hotfix/*` and `release/*` go to `main` |
| Labels | The same `kind/*` as the issue, plus `breaking` or `skip-release` if they apply |
| Draft | Opened at the start; `Ready for review` when CI and description are complete |
| Size | Ideally 250 lines or less; above 500, justify it |

`Closes #12` closes the issue on merge. `Fixes` and `Resolves` also work; for another repo, `Closes owner/repo#12`. If the PR must not close it, use `Refs #12`.

The template lives in `.github/pull_request_template.md` and is copied from `assets/.github/pull_request_template.md`.

## Size

Diff lines: additions plus gross deletions. Lockfiles and generated files inflate the number, so look at them by hand before calling the PR large.

| Size | Lines | Reading |
|---|---|---|
| XS | 0 to 9 | Trivial; merge directly if CI passes |
| S | 10 to 29 | Quick review |
| M | 30 to 99 | Comfortable size |
| L | 100 to 499 | Maximum target; explain the scope |
| XL | 500 to 999 | Warning; split if you can |
| XXL | 1000 or more | Not really reviewed; split before opening |

250 lines is the target, not a law: a 300-line configuration change is reviewed better than a 200-line feature split into five pointless PRs. What is not accepted is an XXL.

## Change only what the task needs

A PR solves one concern. If a refactor, a reformat, a dependency bump or a side fix shows up in the diff, it goes to another issue and another PR.

- Do not reformat files you do not touch.
- Do not bump dependencies "while we are at it".
- Do not fix other people's tests unless they block this change; if you touch them, say so in the description.
- If the change needs a migration or a script, they go in the same PR only if the change is broken without them.

The reason is review: a mixed diff hides the real change and makes it impossible to revert just one part.
