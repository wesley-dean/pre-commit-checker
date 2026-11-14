"""Offline unit tests for the pre-commit configuration checker.

All GitHub API interactions are mocked.  Tests use temporary Jinja2 templates
and encoded YAML payloads; no PAT or live GitHub organization is required.
"""

import base64
import importlib.util
import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from github.GithubException import GithubException, UnknownObjectException


def load_application():
    """Load the application with inert configuration and no network access."""
    application_file = Path(__file__).resolve().parents[1] / "pre_commit_checker.py"
    spec = importlib.util.spec_from_file_location(
        "pre_commit_checker_under_test", application_file
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load pre_commit_checker.py")

    application = importlib.util.module_from_spec(spec)
    with patch.dict(
        os.environ,
        {
            "PAT": "offline-test-placeholder",
            "ORG": "test-organization",
            "DRY_RUN": "True",
            "DELAY": "0",
            "LOGGING": "20",
        },
    ):
        spec.loader.exec_module(application)
    return application


checker = load_application()


def make_repository(name="sample", archived=False, has_issues=True):
    """Return a mock PyGithub Repository with explicit test attributes."""
    repository = MagicMock()
    repository.name = name
    repository.full_name = f"test-organization/{name}"
    repository.archived = archived
    repository.has_issues = has_issues
    return repository


def make_issue(title=None, number=12):
    """Return a mock PyGithub Issue."""
    issue = MagicMock()
    issue.title = title if title is not None else checker.MISSING_ISSUE_TITLE
    issue.number = number
    issue.id = number + 100
    return issue


def make_contents(yaml_text, size=None):
    """Return a mock GitHub Contents object with base64-encoded file data."""
    raw = yaml_text.encode("utf-8")
    return SimpleNamespace(
        size=len(raw) if size is None else size,
        content=base64.b64encode(raw).decode("ascii"),
    )


class DryRunTests(unittest.TestCase):
    """Verify that unexpected dry-run settings do not enable writes."""

    def test_default_is_read_only(self):
        self.assertTrue(checker.is_dry_run())

    def test_true_and_yes_enable_dry_run(self):
        for setting in ("true", "TRUE", "yes", "YeS"):
            with self.subTest(setting=setting):
                self.assertTrue(checker.is_dry_run(setting))

    def test_false_and_no_disable_dry_run(self):
        for setting in ("false", "FALSE", "no", "No"):
            with self.subTest(setting=setting):
                self.assertFalse(checker.is_dry_run(setting))

    def test_unknown_values_fail_closed(self):
        for setting in ("", "1", "0", "maybe", "enabled"):
            with self.subTest(setting=setting):
                self.assertTrue(checker.is_dry_run(setting))


class ExistingIssueTests(unittest.TestCase):
    """Confirm that only an exact open issue title counts as a match."""

    def test_matching_open_issue_is_found(self):
        repository = make_repository()
        repository.get_issues.return_value = [
            make_issue("Unrelated"),
            make_issue(),
        ]

        self.assertTrue(checker.has_pre_commit_issue(repository))
        repository.get_issues.assert_called_once_with(state="open")

    def test_no_issues_is_not_a_match(self):
        repository = make_repository()
        repository.get_issues.return_value = []

        self.assertFalse(checker.has_pre_commit_issue(repository))

    def test_partial_title_does_not_match(self):
        repository = make_repository()
        repository.get_issues.return_value = [
            make_issue(checker.MISSING_ISSUE_TITLE + " (duplicate)"),
        ]

        self.assertFalse(checker.has_pre_commit_issue(repository))

    def test_case_sensitive_title_does_not_match(self):
        repository = make_repository()
        repository.get_issues.return_value = [
            make_issue(checker.MISSING_ISSUE_TITLE.upper()),
        ]

        self.assertFalse(checker.has_pre_commit_issue(repository))

    def test_github_error_is_not_swallowed(self):
        repository = make_repository()
        repository.get_issues.side_effect = GithubException(
            403, {"message": "Forbidden"}
        )

        with self.assertRaises(GithubException):
            checker.has_pre_commit_issue(repository)


class PreCommitConfigTests(unittest.TestCase):
    """Exercise file lookup and the application's current YAML checks."""

    def test_valid_nonempty_repos_is_accepted(self):
        repository = make_repository()
        repository.get_contents.return_value = make_contents(
            "repos:\n  - repo: local\n    hooks:\n      - id: check\n"
        )

        self.assertTrue(checker.has_pre_commit(repository))
        repository.get_contents.assert_called_once_with(
            path=checker.PRE_COMMIT_CONFIG_FILENAME
        )

    def test_missing_file_is_noncompliant(self):
        repository = make_repository()
        repository.get_contents.side_effect = UnknownObjectException(
            404, {"message": "Not Found"}
        )

        self.assertFalse(checker.has_pre_commit(repository))

    def test_empty_file_is_noncompliant(self):
        for size in (0, 1):
            with self.subTest(size=size):
                repository = make_repository()
                repository.get_contents.return_value = make_contents(
                    "x", size=size
                )
                self.assertFalse(checker.has_pre_commit(repository))

    def test_missing_repos_key_is_noncompliant(self):
        repository = make_repository()
        repository.get_contents.return_value = make_contents(
            "default_language_version:\n  python: python3\n"
        )

        self.assertFalse(checker.has_pre_commit(repository))

    def test_empty_repos_is_noncompliant(self):
        repository = make_repository()
        repository.get_contents.return_value = make_contents("repos: []\n")

        self.assertFalse(checker.has_pre_commit(repository))

    def test_invalid_yaml_is_noncompliant(self):
        repository = make_repository()
        repository.get_contents.return_value = make_contents(
            "repos: [unterminated\n"
        )

        self.assertFalse(checker.has_pre_commit(repository))

    def test_github_permission_error_is_propagated(self):
        repository = make_repository()
        repository.get_contents.side_effect = GithubException(
            403, {"message": "Forbidden"}
        )

        with self.assertRaises(GithubException):
            checker.has_pre_commit(repository)

    def test_config_filename_can_be_overridden(self):
        repository = make_repository()
        repository.get_contents.return_value = make_contents(
            "repos:\n  - repo: local\n"
        )

        with patch.object(
            checker, "PRE_COMMIT_CONFIG_FILENAME", ".custom-precommit.yaml"
        ):
            self.assertTrue(checker.has_pre_commit(repository))
        repository.get_contents.assert_called_once_with(
            path=".custom-precommit.yaml"
        )

    def test_nonempty_repos_is_current_validation_boundary(self):
        repository = make_repository()
        repository.get_contents.return_value = make_contents(
            "repos:\n  - placeholder\n"
        )

        # Full pre-commit schema validation is not currently implemented.
        self.assertTrue(checker.has_pre_commit(repository))


class IssueTemplateTests(unittest.TestCase):
    """Test issue writes against local templates and mocked repositories."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)

        folder = Path(self.temporary.name)
        (folder / "open-issue.j2").write_text(
            "Missing {{ filename }} in {{ repository }}",
            encoding="utf-8",
        )
        (folder / "close-issue.j2").write_text(
            "Found {{ filename }} in {{ repository }}",
            encoding="utf-8",
        )
        directory_patch = patch.object(
            checker, "TEMPLATES_DIRECTORY", self.temporary.name
        )
        directory_patch.start()
        self.addCleanup(directory_patch.stop)

    def test_create_issue_renders_template_and_returns_number(self):
        repository = make_repository()
        repository.create_issue.return_value = make_issue(number=47)

        with patch.object(checker, "is_dry_run", return_value=False):
            result = checker.create_issue(repository)

        self.assertEqual(result, 47)
        repository.create_issue.assert_called_once_with(
            title=checker.MISSING_ISSUE_TITLE,
            body=(
                "Missing .pre-commit-config.yaml in "
                "test-organization/sample"
            ),
        )

    def test_create_issue_respects_dry_run(self):
        repository = make_repository()

        with patch.object(checker, "is_dry_run", return_value=True):
            result = checker.create_issue(repository)

        self.assertEqual(result, 0)
        repository.create_issue.assert_not_called()

    def test_create_issue_skips_repositories_without_issues(self):
        repository = make_repository(has_issues=False)

        with patch.object(checker, "is_dry_run", return_value=False):
            result = checker.create_issue(repository)

        self.assertEqual(result, 0)
        repository.create_issue.assert_not_called()

    def test_create_issue_handles_github_failure(self):
        repository = make_repository()
        repository.create_issue.side_effect = GithubException(
            403, {"message": "Forbidden"}
        )

        with patch.object(checker, "is_dry_run", return_value=False):
            result = checker.create_issue(repository)

        self.assertEqual(result, 0)

    def test_create_issue_uses_configured_file_name(self):
        repository = make_repository()
        repository.create_issue.return_value = make_issue(number=5)

        with (
            patch.object(checker, "is_dry_run", return_value=False),
            patch.object(
                checker,
                "PRE_COMMIT_CONFIG_FILENAME",
                ".custom-pre-commit.yaml",
            ),
        ):
            checker.create_issue(repository)

        self.assertIn(
            ".custom-pre-commit.yaml",
            repository.create_issue.call_args.kwargs["body"],
        )

    def test_close_matching_issue_comments_and_closes(self):
        repository = make_repository()
        target = make_issue(number=8)
        unrelated = make_issue("Unrelated", number=9)
        repository.get_issues.return_value = [unrelated, target]

        with patch.object(checker, "is_dry_run", return_value=False):
            count = checker.close_issues(repository)

        self.assertEqual(count, 1)
        target.create_comment.assert_called_once_with(
            "Found .pre-commit-config.yaml in test-organization/sample"
        )
        target.edit.assert_called_once_with(
            state="closed", state_reason="completed"
        )
        unrelated.create_comment.assert_not_called()
        unrelated.edit.assert_not_called()
        repository.get_issues.assert_called_once_with(state="open")

    def test_close_issues_dry_run_never_writes(self):
        repository = make_repository()
        target = make_issue()
        repository.get_issues.return_value = [target]

        with patch.object(checker, "is_dry_run", return_value=True):
            count = checker.close_issues(repository)

        # Existing behavior counts matched issues even during dry runs.
        self.assertEqual(count, 1)
        target.create_comment.assert_not_called()
        target.edit.assert_not_called()

    def test_close_issues_without_matches_returns_zero(self):
        repository = make_repository()
        repository.get_issues.return_value = [make_issue("Unrelated")]

        with patch.object(checker, "is_dry_run", return_value=False):
            count = checker.close_issues(repository)

        self.assertEqual(count, 0)

    def test_close_multiple_matching_issues(self):
        repository = make_repository()
        first = make_issue(number=11)
        second = make_issue(number=12)
        repository.get_issues.return_value = [first, second]

        with patch.object(checker, "is_dry_run", return_value=False):
            count = checker.close_issues(repository)

        self.assertEqual(count, 2)
        first.edit.assert_called_once()
        second.edit.assert_called_once()

    def test_close_issues_swallows_comment_failure(self):
        repository = make_repository()
        target = make_issue()
        target.create_comment.side_effect = GithubException(
            403, {"message": "Forbidden"}
        )
        repository.get_issues.return_value = [target]

        with patch.object(checker, "is_dry_run", return_value=False):
            count = checker.close_issues(repository)

        # Existing behavior increments before attempting the API writes.
        self.assertEqual(count, 1)
        target.edit.assert_not_called()

    def test_close_issues_swallows_edit_failure(self):
        repository = make_repository()
        target = make_issue()
        target.edit.side_effect = GithubException(
            403, {"message": "Forbidden"}
        )
        repository.get_issues.return_value = [target]

        with patch.object(checker, "is_dry_run", return_value=False):
            count = checker.close_issues(repository)

        self.assertEqual(count, 1)
        target.create_comment.assert_called_once_with(
            "Found .pre-commit-config.yaml in test-organization/sample"
        )

    def test_real_bundled_templates_render_offline(self):
        repository = make_repository()
        templates = Path(__file__).resolve().parents[1] / "templates"
        repository.create_issue.return_value = make_issue(number=7)

        with (
            patch.object(checker, "is_dry_run", return_value=False),
            patch.object(checker, "TEMPLATES_DIRECTORY", str(templates)),
        ):
            checker.create_issue(repository)

        body = repository.create_issue.call_args.kwargs["body"]
        self.assertIn(repository.full_name, body)
        self.assertIn(checker.PRE_COMMIT_CONFIG_FILENAME, body)


class ScanWorkflowTests(unittest.TestCase):
    """Drive main() with a fake GitHub client and predictable repositories."""

    def run_scan(
        self,
        repositories,
        configurations=None,
        issues=None,
        new_issue_number=34,
    ):
        """Return all mocks and output from one fully offline scan."""
        configurations = configurations or {}
        issues = issues or {}

        client = MagicMock()
        organization = client.get_organization.return_value
        page = MagicMock()
        page.totalCount = len(repositories)
        page.__iter__.return_value = iter(repositories)
        organization.get_repos.return_value = page

        output = io.StringIO()
        with (
            patch.object(checker, "Github", return_value=client) as factory,
            patch.object(checker, "has_pre_commit") as has_config,
            patch.object(checker, "has_pre_commit_issue") as has_issue,
            patch.object(checker, "create_issue") as create,
            patch.object(checker, "close_issues") as close,
            patch.object(checker.time, "sleep") as sleep,
            redirect_stdout(output),
        ):
            has_config.side_effect = lambda repo: configurations.get(
                repo.name, False
            )
            has_issue.side_effect = lambda repo: issues.get(repo.name, False)
            create.return_value = new_issue_number
            checker.main()

        factory.assert_called_once_with(
            login_or_token=checker.PAT,
            base_url=checker.API_URL,
        )
        client.get_organization.assert_called_once_with(checker.ORG)

        return SimpleNamespace(
            client=client,
            has_config=has_config,
            has_issue=has_issue,
            create=create,
            close=close,
            sleep=sleep,
            output=output.getvalue(),
        )

    def test_empty_organization_is_no_op(self):
        result = self.run_scan([])

        result.has_config.assert_not_called()
        result.has_issue.assert_not_called()
        result.create.assert_not_called()
        result.close.assert_not_called()
        result.sleep.assert_not_called()

    def test_archived_repository_is_skipped(self):
        repository = make_repository("archived", archived=True)
        result = self.run_scan([repository])

        result.has_config.assert_not_called()
        result.has_issue.assert_not_called()
        result.create.assert_not_called()
        result.close.assert_not_called()

    def test_valid_config_without_issue_needs_no_action(self):
        repository = make_repository()
        result = self.run_scan(
            [repository],
            configurations={"sample": True},
        )

        result.has_config.assert_called_once_with(repository)
        result.has_issue.assert_called_once_with(repository)
        result.create.assert_not_called()
        result.close.assert_not_called()

    def test_valid_config_with_issue_closes_it(self):
        repository = make_repository()
        result = self.run_scan(
            [repository],
            configurations={"sample": True},
            issues={"sample": True},
        )

        result.close.assert_called_once_with(repository)
        result.create.assert_not_called()

    def test_invalid_config_with_existing_issue_does_not_duplicate(self):
        repository = make_repository()
        result = self.run_scan(
            [repository],
            issues={"sample": True},
        )

        result.create.assert_not_called()
        result.close.assert_not_called()

    def test_invalid_config_without_issue_creates_one(self):
        repository = make_repository("needs-config")
        result = self.run_scan(
            [repository],
            new_issue_number=58,
        )

        result.create.assert_called_once_with(repository)
        result.close.assert_not_called()
        self.assertIn("Created test-organization/needs-config#58", result.output)

    def test_failed_creation_reports_no_issue_created(self):
        repository = make_repository()
        result = self.run_scan(
            [repository],
            new_issue_number=0,
        )

        result.create.assert_called_once_with(repository)
        self.assertIn("No issue created in sample", result.output)

    def test_sleep_is_only_between_repositories(self):
        repositories = [
            make_repository("first"),
            make_repository("second", archived=True),
            make_repository("third"),
        ]
        result = self.run_scan(
            repositories,
            configurations={"first": True, "third": True},
        )

        self.assertEqual(result.sleep.call_count, 2)
        result.sleep.assert_any_call(0.0)
        self.assertEqual(result.has_config.call_count, 2)

    def test_github_client_error_is_not_masked(self):
        client = MagicMock()
        client.get_organization.side_effect = GithubException(
            403, {"message": "Forbidden"}
        )

        with patch.object(checker, "Github", return_value=client):
            with self.assertRaises(GithubException):
                checker.main()


if __name__ == "__main__":
    unittest.main()
