# Commits and release

## Index

- [Conventional Commits](#conventional-commits)
- [Commit signing](#commit-signing)
- [release-please](#release-please)
- [Gitflow with release-please](#gitflow-with-release-please)

## Conventional Commits

```
<type>(<optional scope>): <summary>
```

- Summary in the imperative, lowercase and without a trailing period: `feat(auth): add SSO login`.
- The scope is optional; use it when it clarifies (`api`, `ui`, `deps`).
- The body explains the why and the how, it does not repeat the diff.
- `!` after the type or the scope marks a breaking change: `feat(api)!: change the /users contract`.
- Equivalent alternative in the footer: `BREAKING CHANGE: <what breaks and how to migrate>`.

| Type | Use |
|---|---|
| `feat` | New functionality |
| `fix` | Bug fix |
| `docs` | Documentation |
| `style` | Formatting, no behaviour change |
| `refactor` | Restructuring with no behaviour change |
| `perf` | Performance improvement |
| `test` | Tests |
| `build` | Build system or dependencies |
| `ci` | CI configuration |
| `chore` | Maintenance that fits nowhere else |
| `revert` | Undo a previous commit, quoting the hash |

One commit, one logical change. If the message needs "and", it is probably two commits.

`.gitmessage` at the repo root (copy `assets/.gitmessage`) reminds you of the format and the Why/How sections:

```bash
git config commit.template .gitmessage
```

## Commit signing

Signing proves that the commit was written by whoever claims it. GitHub marks unsigned commits as unverified, and a ruleset rule can require signing.

SSH, recommended if you already use SSH keys:

```bash
ssh-keygen -t ed25519 -C "your-email" -f ~/.ssh/id_ed25519_signing
git config --global gpg.format ssh
git config --global user.signingkey ~/.ssh/id_ed25519_signing.pub
git config --global commit.gpgsign true
```

Upload the public key to GitHub as a signing key: Settings > SSH and GPG keys > New SSH key > Key type: Signing key. The same entry used for authentication does not work; they are different types.

GPG, if you already have a key:

```bash
gpg --full-generate-key
gpg --list-secret-keys --keyid-format=long
git config --global user.signingkey <KEY_ID>
git config --global commit.gpgsign true
```

Export the public key and paste it into GitHub as a GPG key. In both cases check with `git log --show-signature -1`.

If the repo requires signing, configure tags too: `git config --global tag.gpgsign true`.

## release-please

release-please reads the commits on the release branch and maintains a release PR with the CHANGELOG and the version. Merging that PR creates the tag and the GitHub Release.

Mapping to SemVer:

| Commit | Version |
|---|---|
| `fix:` | patch |
| `feat:` | minor |
| `feat!:`, `fix!:`, any `!` or `BREAKING CHANGE:` | major |
| `docs:`, `chore:`, `ci:`, `test:` and the rest | no release on their own |

On `0.x` versions, a breaking change can bump the minor instead of jumping to `1.0.0`; that is decided with `bump-minor-pre-major` in the configuration.

The release PR is called `chore(main): release <version>`, carries the `autorelease: pending` label and is merged like any other: with green checks. Do not edit the CHANGELOG by hand while the PR is open; if the message of an already merged commit was wrong, add to the PR body:

```
BEGIN_COMMIT_OVERRIDE
fix: the correct message
END_COMMIT_OVERRIDE
```

To force a specific version, a commit with `Release-As: 2.0.0` in the body opens the PR for that version.

Files:

- `.github/workflows/release-please.yml`: workflow, from `assets/.github/workflows/release-please.yml`.
- `release-please-config.json` and `.release-please-manifest.json`: only if you use the manifest. With a single package, `release-type: simple` in the workflow is enough.

`release-type: simple` keeps the version in `version.txt` and the CHANGELOG at the root. If the repo is Node, Python, Rust or similar, change the type to the ecosystem one so it updates the right version file.

### `breaking` and `skip-release` labels

They are a complement, not switches: release-please decides from the commit message, not from the label.

- `breaking`: the PR breaks compatibility. Whoever merges it must ensure that the title and the final commit carry `!` or `BREAKING CHANGE:`. The label warns during review and makes breakages easy to find.
- `skip-release`: the change must not produce a release (CI, documentation, tooling). The commit type (`ci`, `docs`, `chore`) already achieves it; the label makes it explicit for the reviewer.

## Gitflow with release-please

release-please points at `main`, never at `develop`: only what reaches production produces a version.

- The workflow listens for `push` on `main`.
- `develop` is integrated into `main` with a merge commit `--no-ff`. A squash would collapse the history and release-please would lose the individual `feat` and `fix` commits.
- The release PR points at `main` and is merged there.
- After the release, sync `main` back into `develop` so the CHANGELOG and the version file do not diverge.
- A `hotfix/*` lands with squash on `main`, produces a patch and is propagated to `develop`.

If the repo maintains `main-x.x` baselines, each one needs its own configuration with `target-branch`; do not reuse the one for `main`.
