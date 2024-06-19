#!/usr/bin/env python3

"""
@file pre_commit_check.py
@brief Determine if an org's repos have pre-commit configs
@details
This will iterate through the repositories in a GitHub
organization and, for each repository, determine if it has
a non-empty pre-commit configuration.

For repositories without pre-commit configurations, it will
see if an issue already exists in that repository to add
a pre-commit configuration file; if not, it will print
a message (eventually it'll create an issue).
"""

import base64
import logging
import os
import sys
import time

import yaml
from dotenv import load_dotenv
from github import Github
from github.GithubException import GithubException, UnknownObjectException
from jinja2 import Environment, FileSystemLoader

load_dotenv()

##
# @var str PAT
# @brief Personal Access Token for interacting with GitHub
PAT = str(os.getenv("PAT", None))

##
# @var str ORG
# @brief name of GitHub organization to query
ORG = str(os.getenv("ORG", None))

##
# @var str DRY_RUN
# @brief when False, perform read-write operations; otherwise, read-only
DRY_RUN = os.getenv("DRY_RUN", "True")

##
# @var str API_URL
# @brief the URL to the API; default is GitHub.com's API
API_URL = os.getenv("API_URL", "https://api.github.com")

##
# @var float DELAY
# @brief the number of seconds to wait between API calls
DELAY = float(os.getenv("DELAY", "3"))

##
# @var int LOG_LEVEL
# @brief the threshold for displaying logs; higher is quieter
LOG_LEVEL = int(os.getenv("LOGGING", "20"))

logging.basicConfig(level=LOG_LEVEL)

if PAT is None:
    logging.critical("PAT was undefined")
    sys.exit(1)

if ORG is None:
    logging.critical("ORG was undefined")
    sys.exit(1)

##
# @var str MISSING_ISSUE_TITLE
# @brief the title for issues created by this tool
# @details
# In order to determine if there's an issue in the repo
# for a missing or invalid pre-commit configuration file,
# the tool looks for issues with this title.  If it finds
# an open issue with this title, it won't create a new
# issue in the event of a (still) missing / invalid
# pre-commit configuration file.  It doesn't look at
# author or labels or assignees or special strings;
# it just looks for this exact title.
MISSING_ISSUE_TITLE = os.getenv(
    "MISSING_ISSUE_TITLE", "Missing or invalid pre-commit configuration"
)

##
# @var str PRE_COMMIT_CONFIG_FILENAME
# @brief the name of the file to look for
PRE_COMMIT_CONFIG_FILENAME = os.getenv(
    "PRE_COMMIT_CONFIG_FILENAME", ".pre-commit-config.yaml"
)

##
# @var str OPEN_ISSUE_BODY_FILENAME
# @brief the template to use for creating new issues
OPEN_ISSUE_BODY_FILENAME = os.getenv("OPEN_ISSUE_BODY_FILENAME", "open-issue.j2")

##
# @var str CLOSE_ISSUE_BODY_FILENAME
# @brief the template to use when closing issues
CLOSE_ISSUE_BODY_FILENAME = os.getenv("CLOSE_ISSUE_FILENAME", "close-issue.j2")

##
# @var str TEMPLATES_DIRECTORY
# @brief subdirectory of the current directory where to find the templates
TEMPLATES_DIRECTORY = os.getenv("TEMPLATES_DIRECTORY", "templates")


def is_dry_run(value=DRY_RUN):
    """
    @fn is_dry_run()
    @brief determine if we're running in dry run or not
    @details
    A "dry run" is one where we don't actually make any
    changes and it's determined by the global `DRY_RUN`.
    When `DRY_RUN` is set to `False` or `no`, then we'll
    return False (perform write operations); when it's
    set to `True` or `yes, we return `True` (do NOT
    perform write operations); if it's set to anything else,
    we return `True` (do NOT perform write operations).

    By default, we return True (don't perform write
    operations) just to be safe.
    @param value the value to evaluate (default: DRY_RUN)
    @retval False perform write operations
    @retval True don't perform write operations
    @par Examples
    @code
    if is_dry_run():
        print("We won't do the thing")
    else:
        print("We're going to do the thing!!!")
    @endcode
    """

    normalized_value = value.lower()

    if normalized_value in ("true", "yes"):
        return True
    if normalized_value in ("false", "no"):
        return False

    return True


def has_pre_commit_issue(repository):
    """
    @fn has_pre_commit_issue()
    @brief determine if a repo has an issue
    @details
    Given a repository, determine if it has an issue for
    the creation of a pre-commit configuration by looking
    through the open issues and seeing if any match the
    criteria:

    - issue matches the defined title

    Note: the subject much completely match, not just
    a substring.

    @param repository the repository to scan
    @retval True if an open, matching issue exists
    @retval False if not
    @par Example
    @code
    if not has_pre_commit(repo):
        create_issue(repo)
    @endcode
    """

    for issue in repository.get_issues(state="open"):
        if issue.title == MISSING_ISSUE_TITLE:
            return True

    return False


def has_pre_commit(repository):
    """
    @fn has_pre_commit()
    @brief determine if a repo has a non-empty pre-commit config
    @details
    Given a repository, attempt to fetch the pre-commit configuration
    file.  If it's successful and the contents of that file aren't
    empty, return True; if GitHub returns an UnknownObjectException,
    then we know that the file does not exist, so return False.  For
    any other exception, just let the exception through.
    @param repository the repository to check
    @retval True if a non-empty pre-commit config file exists
    @retval False if not
    @par Example
    if not has_pre_commit(repo):
        print("This repo is out of compliance!")
    @endcode
    """

    try:
        contents = repository.get_contents(path=PRE_COMMIT_CONFIG_FILENAME)

        if contents.size <= 1:
            logging.info("pre-commit config is present but empty")
            return False

        try:
            parsed_config = yaml.safe_load(base64.b64decode(contents.content))
            if "repos" not in parsed_config:
                logging.info("invalid pre-commit config -- missing 'repos' dictionary")
                return False

            if len(parsed_config["repos"]) == 0:
                logging.info("invalid pre-commit config -- no defined repos")
                return False

        except yaml.YAMLError:
            logging.info("invalid pre-commit config -- invalid YAML")
            return False

    except UnknownObjectException:
        logging.info("missing pre-commit config")
        return False

    return True


def create_issue(repository):
    """
    @fn create_issue()
    @brief create an issue for tracking adding a pre-commit config file
    @details
    Given a repository, create an issue for tracking the addition of a
    pre-commit configuration file in that repository.
    @param repository the repo to hold the issue
    @returns the id of the issue that was created
    @par Example
    @code
    create_issue(repo)
    @endcode
    """

    j2_environment = Environment(
        loader=FileSystemLoader(TEMPLATES_DIRECTORY), autoescape=True
    )

    issue_template = j2_environment.get_template(OPEN_ISSUE_BODY_FILENAME)

    issue_body = issue_template.render(
        repository=repository.full_name, filename=PRE_COMMIT_CONFIG_FILENAME
    )

    if not is_dry_run():
        try:
            if not repository.has_issues:
                logging.info("repository doesn't support issues")
                return 0

            logging.debug("attempting to create issue")
            issue = repository.create_issue(title=MISSING_ISSUE_TITLE, body=issue_body)
            logging.debug("issue created with id %i", issue.id)
            return issue.number
        except GithubException:
            logging.error("Issue creation failed due to GitHub Exception")

    else:
        logging.info("dry run, so issue not created")

    return 0


def close_issues(repository):
    """
    @fn close_issues()
    @brief scan for open issues; when found, comment on and close them
    @details
    The tool will create an issue in a repository when there is no
    valid pre-commit configuration file (i.e., it's not present, it's
    not valid YAML, or it's missing the required content) via
    create_issue().  This does the opposite and searches for open
    issues and, when found, comments on them and closes them.
    @param repository the repo to scan and potentially update
    @returns the number of issues closed
    @par Example
    @par code
    if has_issue(repo):
        close_issues(repo)
    @par endcode
    """

    j2_environment = Environment(
        loader=FileSystemLoader(TEMPLATES_DIRECTORY), autoescape=True
    )

    comment_template = j2_environment.get_template(CLOSE_ISSUE_BODY_FILENAME)

    comment_body = comment_template.render(
        repository=repository.full_name, filename=PRE_COMMIT_CONFIG_FILENAME
    )

    closed_issues = 0

    for issue in repository.get_issues(state="open"):
        if issue.title == MISSING_ISSUE_TITLE:
            closed_issues += 1
            logging.info("Closing issue #%i", issue.number)

            if not is_dry_run():
                try:
                    logging.debug("  Adding comment")
                    issue.create_comment(comment_body)
                    logging.debug("  Marking issue as completed")
                    issue.edit(state="closed", state_reason="completed")
                except GithubException:
                    logging.error("Issue closing failed due to GitHuh Exception")
            else:
                logging.info("dry run, so issue not closed")

    return closed_issues


def main():
    """
    @fn main()
    @brief the main function
    """

    logging.debug('Using PAT "%s**************************"', PAT[:8])
    logging.debug('Using ORG "%s"', ORG)

    logging.basicConfig(level=logging.INFO)
    github = Github(login_or_token=PAT, base_url=API_URL)

    organization_object = github.get_organization(ORG)

    repos = organization_object.get_repos()

    repo_count = 0
    repo_total = repos.totalCount

    for repo in repos:
        repo_count += 1

        logging.info("%i / %i: '%s'", repo_count, repo_total, repo.name)

        if repo.archived:
            logging.info("  repo is archived; skipping")
        else:
            if has_pre_commit(repo):
                logging.info("  has pre-commit")
                if has_pre_commit_issue(repo):
                    close_issues(repo)
            else:
                logging.info("  Does NOT have pre-commit")
                if has_pre_commit_issue(repo):
                    logging.info("    has issue")
                else:
                    logging.info("    NEEDS issue")
                    issue_id = create_issue(repo)

                    if issue_id == 0:
                        print(f"No issue created in {repo.name}")
                    else:
                        print(f"Created {ORG}/{repo.name}#{issue_id}")
        if repo_count != repo_total:
            time.sleep(DELAY)


if __name__ == "__main__":
    main()
