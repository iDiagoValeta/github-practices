import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "github-practices" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import audit  # noqa: E402


FULL_RULES = [
    "pull_request",
    "required_status_checks",
    "non_fast_forward",
    "deletion",
    "required_linear_history",
]


def a_rule(rule_type):
    # required_status_checks without configured checks blocks nothing: the API
    # only counts it as a real rule when it brings the list.
    if rule_type == "required_status_checks":
        return {
            "type": rule_type,
            "parameters": {"required_status_checks": [{"context": "ci"}]},
        }
    return {"type": rule_type}


def a_ruleset(name="main", rules=None, enforcement="active", include=None):
    return {
        "id": 1,
        "name": name,
        "target": "branch",
        "enforcement": enforcement,
        "conditions": {
            "ref_name": {"include": include or ["~DEFAULT_BRANCH"], "exclude": []}
        },
        "rules": [a_rule(t) for t in (rules or FULL_RULES)],
    }


def a_pr(number=1, valid_name=True, linked=True, added=10, deleted=5,
         hours=4, title=None, body=""):
    return {
        "number": number,
        "title": title if title is not None else ("GH-%d fix" % number if linked else "loose fix"),
        "body": body,
        "headRefName": (
            ("feature/GH-%d-fix" % number)
            if valid_name and linked
            else (("internal/fix-%d" % number) if valid_name else "fix_%d" % number)
        ),
        "additions": added,
        "deletions": deleted,
        "createdAt": "2026-01-01T00:00:00Z",
        "mergedAt": "2026-01-01T%02d:00:00Z" % min(hours, 23),
        "isDraft": False,
        "closingIssuesReferences": [{"number": number}] if linked else [],
    }


def base_state(**overrides):
    state = {
        "repo": {
            "nameWithOwner": "owner/repo",
            "default_branch": "main",
            "allow_squash_merge": True,
            "allow_merge_commit": False,
            "allow_rebase_merge": False,
            "security_and_analysis": {
                "secret_scanning": {"status": "enabled"},
                "secret_scanning_push_protection": {"status": "enabled"},
            },
        },
        "branches": ["main"],
        "labels": list(audit.REQUIRED_LABELS),
        "prs": [a_pr()],
        "rulesets": {"status": "ok", "rulesets": [a_ruleset()]},
        "contributors": 1,
        "tags": [],
        "local": {
            "is_git_repo": True,
            "pr_template": ".github/pull_request_template.md",
            "issue_templates": [
                {"name": "bug.yml", "labels": ["kind/bug"]},
                {"name": "feature.yml", "labels": ["kind/feature"]},
            ],
            "codeowners": True,
            "dependabot": True,
            "release_please": True,
            "gitmessage": True,
            "commit_subjects": ["feat: add login", "fix: correct edge"],
        },
    }
    state.update(overrides)
    return state


def finding_ids(findings):
    return {f["id"] for f in findings}


class HealthyStateTests(unittest.TestCase):
    def test_healthy_state_has_no_severe_findings(self):
        findings = audit.evaluate(base_state())
        severe = [f for f in findings if f["severity"] in ("high", "medium")]
        self.assertEqual(severe, [])

    def test_every_finding_has_the_required_shape(self):
        findings = audit.evaluate(base_state(labels=[]))
        self.assertTrue(findings)
        for finding in findings:
            self.assertEqual(
                set(finding), {"id", "area", "severity", "message", "fix"}
            )
            self.assertIn(finding["severity"], ("high", "medium", "low", "info"))
            self.assertTrue(finding["message"])
            self.assertTrue(finding["fix"])


class PrTemplateTests(unittest.TestCase):
    def test_missing_pr_template_emits_a_concrete_finding(self):
        state = base_state()
        state["local"]["pr_template"] = None
        findings = audit.evaluate(state)
        self.assertIn("pr.template-missing", finding_ids(findings))
        finding = next(f for f in findings if f["id"] == "pr.template-missing")
        self.assertEqual(finding["severity"], "high")
        self.assertIn("pull_request_template", finding["fix"])


class IssueTemplatesTests(unittest.TestCase):
    def test_no_issue_templates(self):
        state = base_state()
        state["local"]["issue_templates"] = []
        self.assertIn("issues.forms-missing", finding_ids(audit.evaluate(state)))

    def test_templates_without_kind_label(self):
        state = base_state()
        state["local"]["issue_templates"] = [
            {"name": "bug.yml", "labels": []},
            {"name": "feature.yml", "labels": ["kind/feature"]},
        ]
        self.assertIn("issues.forms-incomplete", finding_ids(audit.evaluate(state)))

    def test_missing_feature_form(self):
        state = base_state()
        state["local"]["issue_templates"] = [
            {"name": "bug.yml", "labels": ["kind/bug"]},
        ]
        self.assertIn("issues.forms-incomplete", finding_ids(audit.evaluate(state)))


class LocalFilesTests(unittest.TestCase):
    def test_dependabot_absent(self):
        state = base_state()
        state["local"]["dependabot"] = False
        self.assertIn("dependabot.missing", finding_ids(audit.evaluate(state)))

    def test_release_please_absent(self):
        state = base_state()
        state["local"]["release_please"] = False
        self.assertIn("release.release-please-missing", finding_ids(audit.evaluate(state)))

    def test_codeowners_only_required_with_several_maintainers(self):
        state = base_state()
        state["local"]["codeowners"] = False
        state["contributors"] = 1
        self.assertNotIn("codeowners.missing", finding_ids(audit.evaluate(state)))
        state["contributors"] = 3
        self.assertIn("codeowners.missing", finding_ids(audit.evaluate(state)))

    def test_optional_gitmessage_is_only_low(self):
        state = base_state()
        state["local"]["gitmessage"] = False
        findings = audit.evaluate(state)
        finding = next(f for f in findings if f["id"] == "commits.gitmessage-missing")
        self.assertEqual(finding["severity"], "low")

    def test_non_conventional_commits(self):
        state = base_state()
        state["local"]["commit_subjects"] = [
            "feat: one", "manual fix", "another change", "fix: two",
        ]
        findings = audit.evaluate(state)
        finding = next(f for f in findings if f["id"] == "commits.conventional")
        self.assertIn("50", finding["message"])

    def test_unverifiable_contributors_emit_codeowners_info(self):
        state = base_state()
        state["contributors"] = None
        state["local"]["codeowners"] = False
        finding = next(
            f for f in audit.evaluate(state) if f["id"] == "codeowners.missing"
        )
        self.assertEqual(finding["severity"], "info")
        self.assertIn("not verifiable", finding["message"])

    def test_local_omitted_for_a_different_repo_invents_no_findings(self):
        state = base_state(local=None)
        findings = audit.evaluate(state)
        self.assertNotIn("pr.template-missing", finding_ids(findings))
        self.assertNotIn("dependabot.missing", finding_ids(findings))
        self.assertNotIn("commits.conventional", finding_ids(findings))
        info = next(f for f in findings if f["id"] == "local.no-verificado")
        self.assertEqual(info["severity"], "info")


class RemoteRepoTests(unittest.TestCase):
    def test_normalizes_https_ssh_and_without_git(self):
        cases = [
            "https://github.com/Owner/Repo.git",
            "https://github.com/Owner/Repo",
            "git@github.com:Owner/Repo.git",
            "ssh://git@github.com/Owner/Repo.git",
        ]
        for url in cases:
            with self.subTest(url=url):
                self.assertEqual(audit._normalize_repo(url), "owner/repo")

    def test_non_github_url_is_not_normalized(self):
        self.assertIsNone(audit._normalize_repo("https://gitlab.com/owner/repo.git"))


class LabelsTests(unittest.TestCase):
    def test_missing_required_labels(self):
        state = base_state()
        state["labels"] = ["kind/feature", "kind/bug"]
        findings = audit.evaluate(state)
        finding = next(f for f in findings if f["id"] == "labels.missing")
        self.assertIn("kind/security", finding["message"])
        self.assertIn("breaking", finding["message"])


class BranchModelTests(unittest.TestCase):
    def test_develop_as_default_is_gitflow(self):
        state = base_state()
        state["repo"]["default_branch"] = "develop"
        state["branches"] = ["main", "develop"]
        model = audit.detect_model(state["branches"], state["repo"]["default_branch"])
        self.assertEqual(model, "gitflow")

    def test_develop_not_default_is_tbd_and_warns(self):
        state = base_state()
        state["branches"] = ["main", "develop"]
        findings = audit.evaluate(state)
        self.assertIn("branch.develop-unused", finding_ids(findings))
        report = audit.build_report("owner/repo", "/tmp", state)
        self.assertEqual(report["model"]["current"], "tbd")

    def test_single_contributor_without_tags_recommends_tbd(self):
        state = base_state()
        recommended, reasons = audit.recommend_model("tbd", state)
        self.assertEqual(recommended, "tbd")
        self.assertTrue(reasons)

    def test_several_contributors_and_tags_recommend_gitflow(self):
        state = base_state()
        state["contributors"] = 5
        state["tags"] = ["v1.0.0", "v1.1.0", "v2.0.0"]
        recommended, _ = audit.recommend_model("tbd", state)
        self.assertEqual(recommended, "gitflow")

    def test_release_branches_are_a_gitflow_signal(self):
        state = base_state()
        state["branches"] = ["main", "release/1.0"]
        state["contributors"] = 2
        recommended, _ = audit.recommend_model("tbd", state)
        self.assertEqual(recommended, "gitflow")

    def test_gitflow_with_one_contributor_and_no_tags_is_reviewed(self):
        state = base_state()
        recommended, _ = audit.recommend_model("gitflow", state)
        self.assertEqual(recommended, "tbd")

    def test_insufficient_data_keeps_the_current_model(self):
        state = base_state()
        state["contributors"] = None
        state["branches"] = None
        state["tags"] = None
        recommended, reasons = audit.recommend_model("gitflow", state)
        self.assertEqual(recommended, "gitflow")
        self.assertIn("insufficient data", " ".join(reasons).lower())
        self.assertIn("not verifiable", " ".join(reasons))


class MergeTests(unittest.TestCase):
    def test_tbd_with_merge_commit_allowed(self):
        state = base_state()
        state["repo"]["allow_merge_commit"] = True
        findings = audit.evaluate(state)
        finding = next(f for f in findings if f["id"] == "merge.settings")
        self.assertIn("merge commit", finding["message"])

    def test_tbd_without_squash(self):
        state = base_state()
        state["repo"]["allow_squash_merge"] = False
        self.assertIn("merge.settings", finding_ids(audit.evaluate(state)))

    def test_gitflow_needs_merge_commit(self):
        state = base_state()
        state["repo"]["default_branch"] = "develop"
        state["branches"] = ["main", "develop"]
        state["rulesets"] = {
            "status": "ok",
            "rulesets": [
                a_ruleset("develop"),
                {
                    "id": 2,
                    "name": "main",
                    "target": "branch",
                    "enforcement": "active",
                    "conditions": {"ref_name": {"include": ["refs/heads/main"], "exclude": []}},
                    "rules": [{"type": t} for t in FULL_RULES],
                },
            ],
        }
        state["local"]["commit_subjects"] = ["feat: x"]
        self.assertIn("merge.settings", finding_ids(audit.evaluate(state)))


class ProtectionTests(unittest.TestCase):
    def test_unverifiable_rulesets_do_not_fail(self):
        state = base_state()
        state["rulesets"] = {"status": "unavailable", "rulesets": [], "detail": "403"}
        findings = audit.evaluate(state)
        self.assertIn("protection.unverifiable", finding_ids(findings))
        self.assertNotIn("protection.ruleset-missing", finding_ids(findings))

    def test_no_ruleset_on_the_default_branch(self):
        state = base_state()
        state["rulesets"] = {"status": "ok", "rulesets": []}
        self.assertIn("protection.ruleset-missing", finding_ids(audit.evaluate(state)))

    def test_ruleset_without_pull_request(self):
        state = base_state()
        rules = [t for t in FULL_RULES if t != "pull_request"]
        state["rulesets"] = {"status": "ok", "rulesets": [a_ruleset(rules=rules)]}
        self.assertIn("protection.pull-request", finding_ids(audit.evaluate(state)))

    def test_tbd_without_linear_history(self):
        state = base_state()
        rules = [t for t in FULL_RULES if t != "required_linear_history"]
        state["rulesets"] = {"status": "ok", "rulesets": [a_ruleset(rules=rules)]}
        self.assertIn("protection.linear-history", finding_ids(audit.evaluate(state)))

    def test_force_push_and_deletion(self):
        state = base_state()
        rules = [t for t in FULL_RULES if t not in ("non_fast_forward", "deletion")]
        state["rulesets"] = {"status": "ok", "rulesets": [a_ruleset(rules=rules)]}
        found = finding_ids(audit.evaluate(state))
        self.assertIn("protection.force-push", found)
        self.assertIn("protection.deletion", found)

    def test_status_checks_is_low_and_refers_to_ci(self):
        state = base_state()
        rules = [t for t in FULL_RULES if t != "required_status_checks"]
        state["rulesets"] = {"status": "ok", "rulesets": [a_ruleset(rules=rules)]}
        finding = next(
            f
            for f in audit.evaluate(state)
            if f["id"] == "protection.status-checks"
        )
        self.assertEqual(finding["severity"], "low")
        self.assertIn("stable names", finding["message"])

    def test_status_checks_without_checks_does_not_count(self):
        state = base_state()
        ruleset = a_ruleset()
        for rule in ruleset["rules"]:
            if rule["type"] == "required_status_checks":
                rule["parameters"] = {"required_status_checks": []}
        state["rulesets"] = {"status": "ok", "rulesets": [ruleset]}
        self.assertIn("protection.status-checks", finding_ids(audit.evaluate(state)))

    def test_rules_are_evaluated_per_target_branch(self):
        state = base_state()
        state["repo"]["default_branch"] = "develop"
        state["branches"] = ["main", "develop"]
        state["rulesets"] = {
            "status": "ok",
            "rulesets": [
                a_ruleset(
                    name="develop",
                    rules=[t for t in FULL_RULES if t != "pull_request"],
                    include=["refs/heads/develop"],
                ),
                a_ruleset(
                    name="main",
                    rules=FULL_RULES,
                    include=["refs/heads/main"],
                ),
            ],
        }
        finding = next(
            f
            for f in audit.evaluate(state)
            if f["id"] == "protection.pull-request"
        )
        self.assertIn("develop", finding["message"])

    def test_assets_do_not_include_status_checks(self):
        assets = Path(__file__).resolve().parents[1] / "github-practices" / "assets"
        for name in ("tbd.json", "gitflow.json"):
            data = json.loads((assets / "rulesets" / name).read_text(encoding="utf-8"))
            types = {rule["type"] for rule in data["rules"]}
            with self.subTest(asset=name):
                self.assertNotIn("required_status_checks", types)


class SecurityTests(unittest.TestCase):
    def test_secret_scanning_disabled(self):
        state = base_state()
        state["repo"]["security_and_analysis"]["secret_scanning"] = {
            "status": "disabled"
        }
        self.assertIn("security.secret-scanning", finding_ids(audit.evaluate(state)))

    def test_unavailable_feature_is_not_reported_as_off(self):
        state = base_state()
        state["repo"]["security_and_analysis"] = {}
        findings = audit.evaluate(state)
        self.assertEqual(
            [f for f in findings if f["id"].startswith("security.secret")], []
        )
        self.assertNotIn("security.push-protection", finding_ids(findings))


class MetricsTests(unittest.TestCase):
    def test_linked_issue_percentage(self):
        state = base_state()
        state["prs"] = [
            a_pr(1, linked=True),
            a_pr(2, linked=True),
            a_pr(3, linked=False),
            a_pr(4, linked=False),
        ]
        report = audit.build_report("owner/repo", "/tmp", state)
        self.assertEqual(report["metrics"]["issue_link_pct"], 50.0)
        finding = next(f for f in report["findings"] if f["id"] == "prs.issue-link")
        self.assertIn("50", finding["message"])

    def test_mention_in_title_without_keyword_does_not_count(self):
        state = base_state()
        pr = a_pr(1, linked=False, title="GH-1 fix")
        state["prs"] = [pr]
        report = audit.build_report("owner/repo", "/tmp", state)
        self.assertEqual(report["metrics"]["issue_link_pct"], 0.0)
        finding = next(f for f in report["findings"] if f["id"] == "prs.issue-mention")
        self.assertEqual(finding["severity"], "info")
        self.assertIn("Mention without a link", finding["message"])

    def test_issue_linked_by_keyword_in_body(self):
        state = base_state()
        state["prs"] = [a_pr(1, linked=False, body="Closes #12")]
        report = audit.build_report("owner/repo", "/tmp", state)
        self.assertEqual(report["metrics"]["issue_link_pct"], 100.0)

    def test_issue_linked_by_issue_url(self):
        state = base_state()
        state["prs"] = [
            a_pr(
                1,
                linked=False,
                body="Fixes https://github.com/owner/repo/issues/12",
            )
        ]
        report = audit.build_report("owner/repo", "/tmp", state)
        self.assertEqual(report["metrics"]["issue_link_pct"], 100.0)

    def test_technical_key_in_title_does_not_count_as_issue(self):
        state = base_state()
        state["prs"] = [a_pr(1, linked=False, title="fix: parses ISO-8601")]
        report = audit.build_report("owner/repo", "/tmp", state)
        self.assertEqual(report["metrics"]["issue_link_pct"], 0.0)

    def test_median_size_and_median_hours(self):
        state = base_state()
        state["prs"] = [
            a_pr(1, added=100, deleted=100, hours=2),
            a_pr(2, added=200, deleted=50, hours=6),
            a_pr(3, added=300, deleted=200, hours=10),
        ]
        report = audit.build_report("owner/repo", "/tmp", state)
        self.assertEqual(report["metrics"]["median_size"], 250)
        self.assertEqual(report["metrics"]["median_hours"], 6.0)

    def test_large_median_size_warns(self):
        state = base_state()
        state["prs"] = [a_pr(i, added=600, deleted=10) for i in range(1, 4)]
        finding = next(
            f for f in audit.evaluate(state) if f["id"] == "prs.size"
        )
        self.assertIn("610", finding["message"])

    def test_invalid_pr_branches(self):
        state = base_state()
        state["prs"] = [
            a_pr(1, valid_name=True),
            a_pr(2, valid_name=False),
        ]
        findings = audit.evaluate(state)
        finding = next(f for f in findings if f["id"] == "prs.branch-names")
        self.assertIn("50", finding["message"])
        self.assertIn("fix_2", finding["message"])


class ReportTests(unittest.TestCase):
    def test_json_serializable_and_with_model(self):
        report = audit.build_report("owner/repo", "/tmp", base_state())
        text = json.dumps(report)
        self.assertIn("owner/repo", text)
        self.assertIn(report["model"]["current"], ("tbd", "gitflow"))
        self.assertIn("recommended", report["model"])

    def test_markdown_by_severity(self):
        state = base_state(labels=[])
        report = audit.build_report("owner/repo", "/tmp", state)
        text = audit.render_markdown(report)
        self.assertIn("# GitHub practices audit", text)
        self.assertIn("## Findings", text)
        self.assertIn("medium", text)
        self.assertIn("labels.missing", text)

    def test_findings_sorted_by_severity(self):
        state = base_state()
        state["local"]["pr_template"] = None
        state["local"]["gitmessage"] = False
        findings = audit.evaluate(state)
        order = {"high": 0, "medium": 1, "low": 2, "info": 3}
        severities = [order[f["severity"]] for f in findings]
        self.assertEqual(severities, sorted(severities))


class CollectLocalTests(unittest.TestCase):
    def test_detects_local_files_and_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / ".github" / "ISSUE_TEMPLATE").mkdir(parents=True)
            (base / ".github" / "PULL_REQUEST_TEMPLATE.md").write_text("## What changes\n")
            (base / ".github" / "ISSUE_TEMPLATE" / "bug.yml").write_text(
                "labels:\n  - kind/bug\n"
            )
            (base / ".github" / "ISSUE_TEMPLATE" / "feature.yml").write_text(
                "labels: [kind/feature]\n"
            )
            (base / ".github" / "dependabot.yml").write_text("version: 2\n")
            (base / ".github" / "workflows").mkdir()
            (base / ".github" / "workflows" / "release.yml").write_text(
                "uses: googleapis/release-please-action@v5\n"
            )
            (base / ".github" / "CODEOWNERS").write_text("* @maintainer\n")
            (base / ".gitmessage").write_text("Why:\nHow:\n")

            local = audit.collect_local(tmp)

            self.assertEqual(local["pr_template"], ".github/PULL_REQUEST_TEMPLATE.md")
            self.assertEqual(
                [template["labels"] for template in local["issue_templates"]],
                [["kind/bug"], ["kind/feature"]],
            )
            self.assertTrue(local["dependabot"])
            self.assertTrue(local["release_please"])
            self.assertTrue(local["codeowners"])
            self.assertTrue(local["gitmessage"])
            self.assertFalse(local["is_git_repo"])
            self.assertEqual(local["commit_subjects"], [])

    def test_template_in_uppercase_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            directory = base / ".github" / "PULL_REQUEST_TEMPLATE"
            directory.mkdir(parents=True)
            (directory / "normal.md").write_text("## What changes\n")

            local = audit.collect_local(tmp)

            self.assertEqual(
                local["pr_template"], ".github/PULL_REQUEST_TEMPLATE"
            )

    def test_empty_directory_invents_no_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            local = audit.collect_local(tmp)
            self.assertIsNone(local["pr_template"])
            self.assertEqual(local["issue_templates"], [])
            self.assertFalse(local["dependabot"])
            self.assertFalse(local["release_please"])
            self.assertFalse(local["codeowners"])
            self.assertFalse(local["gitmessage"])

    def test_config_yml_does_not_count_as_a_form(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / ".github" / "ISSUE_TEMPLATE").mkdir(parents=True)
            (base / ".github" / "ISSUE_TEMPLATE" / "config.yml").write_text(
                "blank_issues_enabled: false\n"
            )

            local = audit.collect_local(tmp)

            self.assertEqual(local["issue_templates"], [])

    def test_merge_commits_do_not_enter_the_sample(self):
        def git(*args):
            subprocess.run(
                ["git", "-c", "user.name=T", "-c", "user.email=t@t", *args],
                cwd=tmp,
                check=True,
                capture_output=True,
            )

        with tempfile.TemporaryDirectory() as tmp:
            git("init", "-q", "-b", "main")
            git("commit", "--allow-empty", "-m", "feat: initial")
            git("checkout", "-q", "-b", "feature")
            git("commit", "--allow-empty", "-m", "fix: fix")
            git("checkout", "-q", "main")
            git("merge", "--no-ff", "feature", "-m", "Merge branch 'feature'")

            local = audit.collect_local(tmp)

            self.assertEqual(
                sorted(local["commit_subjects"]),
                ["feat: initial", "fix: fix"],
            )


class CollectPrsTests(unittest.TestCase):
    def test_window_sorts_by_merged_at_and_trims(self):
        data = [
            {"number": 1, "mergedAt": "2026-01-01T00:00:00Z"},
            {"number": 2, "mergedAt": "2026-01-03T00:00:00Z"},
            {"number": 3, "mergedAt": "2026-01-02T00:00:00Z"},
        ]
        with mock.patch.object(
            audit, "_gh_json", return_value=(data, None)
        ) as gh_json:
            prs = audit.collect_prs("owner/repo", 2)

        self.assertEqual([pr["number"] for pr in prs], [2, 3])
        arguments = gh_json.call_args[0][0]
        self.assertEqual(arguments[arguments.index("--limit") + 1], "6")


class CliTests(unittest.TestCase):
    def test_without_gh_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            audit.shutil, "which", return_value=None
        ):
            self.assertEqual(audit.main(["--path", tmp]), 2)

    def test_gh_not_authenticated_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            audit.shutil, "which", return_value="/usr/bin/gh"
        ), mock.patch.object(
            audit, "_run", return_value=(1, "", "not logged in")
        ):
            self.assertEqual(audit.main(["--path", tmp]), 2)

    def test_gh_ready_when_auth_status_exits_0(self):
        with mock.patch.object(
            audit.shutil, "which", return_value="/usr/bin/gh"
        ), mock.patch.object(audit, "_run", return_value=(0, "", "")):
            self.assertEqual(audit._gh_ready(), (True, ""))

    def test_different_repo_and_path_skip_local_checks(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            audit, "_gh_ready", return_value=(True, "")
        ), mock.patch.object(
            audit, "_remote_origin", return_value="https://github.com/other/repo.git"
        ), mock.patch.object(
            audit, "collect_state", return_value=base_state(local=None)
        ) as collect_state:
            output = io.StringIO()
            with mock.patch("sys.stdout", output):
                code = audit.main(["--repo", "owner/repo", "--path", tmp])

        self.assertEqual(code, 0)
        self.assertFalse(collect_state.call_args.kwargs["include_local"])
        self.assertIn("local.no-verificado", output.getvalue())


if __name__ == "__main__":
    unittest.main()
