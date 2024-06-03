#!/usr/bin/env python

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

import logging
import os

from github import Github
from github.GithubException import UnknownObjectException
from dotenv import load_dotenv

load_dotenv()
PAT = os.environ["PAT"]
ORG = os.environ["ORG"]

if "MISSING_ISSUE_TITLE" in os.environ:
    MISSING_ISSUE_TITLE = os.environ["MISSING_ISSUE_TITLE"]
else:
    MISSING_ISSUE_TITLE = "Missing pre-commit configuration"


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
        pre_commit_content = repository.get_contents(path=".pre-commit-config.yaml")
    except UnknownObjectException:
        logging.debug("missing pre-commit config")
        return False

    if not pre_commit_content:
        logging.debug("empty pre-commit config")
        return False

    return True


def main():
    """
    @fn main()
    @brief the main function
    """

    logging.debug('Using PAT "%s**************************"', PAT[:8])
    logging.debug('Using ORG "%s"', ORG)

    logging.basicConfig(level=logging.INFO)
    g = Github(PAT)

    for repo in g.get_organization(ORG).get_repos():
        logging.info("Checking repo '%s'", repo.name)

        if repo.archived:
            logging.info("  repo is archived; skipping")
        else:
            if has_pre_commit(repo):
                print("  has pre-commit")
            else:
                print("  Does NOT have pre-commit")
                if has_pre_commit_issue(repo):
                    print("    has issue")
                else:
                    print("    NEEDS issue")


if __name__ == "__main__":
    main()
