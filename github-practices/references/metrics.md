# Metrics

## Index

- [What they measure](#what-they-measure)
- [Thresholds](#thresholds)
- [Calculating with gh](#calculating-with-gh)
- [When not to trust them](#when-not-to-trust-them)

## What they measure

Inspired by DORA, computed over the latest merged PRs. They measure the flow of the team and the repo, never the performance of a person: a large or slow PR says something about the process, the size of the tasks and who reviews, not about who writes.

Default window: 30 merged PRs. Fewer than 15 is not enough for conclusions, only to spot an odd case.

`audit.py` asks `gh pr list` for a margin of 3N and then sorts by `mergedAt` before keeping N. It is an approximation: the `gh` list sorts by creation date, so an old PR merged late can fall outside the window. The GraphQL query below asks directly for the latest by `UPDATED_AT`.

## Thresholds

| Metric | Elite | High | Medium | Low |
|---|---|---|---|---|
| Time to first review | 12 h or less | 12 to 24 h | 24 to 48 h | more than 48 h |
| Review time | 18 h or less | 18 to 36 h | 36 to 72 h | more than 72 h |
| PR size (lines) | 250 or less | 250 to 500 | 500 to 1000 | more than 1000 |
| PR with linked issue | 90 % or more | 75 to 90 % | 50 to 75 % | less than 50 % |
| Lead time | 48 h or less | 48 to 168 h | 168 to 336 h | more than 336 h |
| Deployment frequency | more than 1 per day | 0.5 to 1 per day | 0.15 to 0.5 per day | 0.15 per day or less |

Definitions:

- Time to first review: first review submitted minus PR creation.
- Review time: merge minus first review. It measures the queue after the first review.
- Size: additions plus gross deletions of the diff. Lockfiles and generated files inflate the number; look at them by hand before concluding.
- PR with linked issue: only `closingIssuesReferences` or a closing keyword (`Closes`, `Fixes`, `Resolves`) in the body counts. A mention in the title or the branch links nothing.
- Lead time: merge minus PR creation. It is a proxy for cycle time, not the time since the first commit.
- Deployment frequency: deployments or releases per day in the window.

## Calculating with gh

```bash
REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)

gh api graphql -f query='
query ($owner: String!, $repo: String!, $n: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequests(first: $n, states: MERGED, orderBy: {field: UPDATED_AT, direction: DESC}) {
      nodes {
        number
        createdAt
        mergedAt
        isDraft
        additions
        deletions
        closingIssuesReferences(first: 1) { totalCount }
        reviews(last: 30) { nodes { submittedAt } }
      }
    }
  }
}' -f owner="${REPO%/*}" -f repo="${REPO#*/}" -F n=30 > /tmp/prs.json
```

Median size:

```bash
jq '[.data.repository.pullRequests.nodes[] | .additions + .deletions]
    | sort | .[(length / 2) | floor]' /tmp/prs.json
```

Percentage with a linked issue:

```bash
jq '.data.repository.pullRequests.nodes as $prs
    | [ $prs[] | select(.closingIssuesReferences.totalCount > 0) ] | length
    | . * 100 / ($prs | length) | floor' /tmp/prs.json
```

Median time to first review, in hours:

```bash
jq '[.data.repository.pullRequests.nodes[]
     | select((.reviews.nodes | map(select(.submittedAt != null)) | length) > 0)
     | ((.reviews.nodes | map(select(.submittedAt != null) | .submittedAt) | min | fromdateiso8601)
        - (.createdAt | fromdateiso8601)) / 3600]
    | sort | .[(length / 2) | floor]' /tmp/prs.json
```

Median review time, in hours:

```bash
jq '[.data.repository.pullRequests.nodes[]
     | select((.reviews.nodes | map(select(.submittedAt != null)) | length) > 0)
     | ((.mergedAt | fromdateiso8601)
        - (.reviews.nodes | map(select(.submittedAt != null) | .submittedAt) | min | fromdateiso8601)) / 3600]
    | sort | .[(length / 2) | floor]' /tmp/prs.json
```

Median lead time, in hours:

```bash
jq '[.data.repository.pullRequests.nodes[]
     | ((.mergedAt | fromdateiso8601) - (.createdAt | fromdateiso8601)) / 3600]
    | sort | .[(length / 2) | floor]' /tmp/prs.json
```

Deployment frequency, last 90 days:

```bash
SINCE=$(python3 -c 'from datetime import datetime, timedelta, timezone; print((datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%SZ"))')

gh api "repos/$REPO/deployments?per_page=100" --paginate --slurp \
  | jq --arg since "$SINCE" '[.[][] | select(.created_at > $since)] | length'
```

If the repo does not record deployments, use releases as a proxy and say so when presenting the number:

```bash
gh release list --repo "$REPO" --limit 100 --json publishedAt \
  | jq --arg since "$SINCE" '[.[] | select(.publishedAt > $since)] | length'
```

Divide the total by 90 to get the daily frequency.

The percentage of PRs that went through draft cannot be taken from `isDraft`: that field only says whether it is a draft now. To measure it properly you have to read the `ReadyForReviewEvent` and `ConvertToDraftEvent` events from each PR's timeline, which is expensive and only done if the question matters.

## When not to trust them

- Few PRs: with fewer than 15, an outlier moves the median and any comparison is noise.
- Single-person repos: there is no review wait to measure; the bottleneck is the person and the metrics disguise it as process.
- Bots and dependencies: Dependabot and release-please PRs inflate the volume and the size. Filter them or count them separately.
- A squash erases the iterations: review time includes waits that the history does not show.
- Weekends and time zones: 48 h can be two working days or five.
- Median versus mean: use the median; the mean is moved by a single abandoned PR.
- The number is not the goal. If the team splits PRs to lower the metric, the metric stops measuring what mattered.
