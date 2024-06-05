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

import logging
import os
import yaml

from jinja2 import Environment, FileSystemLoader
from github import Github
from github.GithubException import UnknownObjectException
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)

load_dotenv()
PAT = os.environ["PAT"]
ORG = os.environ["ORG"]

MISSING_ISSUE_TITLE = os.getenv(
    "MISSING_ISSUE_TITLE", "Missing or invalid pre-commit configuration"
)

PRE_COMMIT_CONFIG_FILENAME = os.getenv(
    "PRE_COMMIT_CONFIG_FILENAME", ".pre-commit-config.yaml"
)

MISSING_ISSUE_BODY_FILENAME = os.getenv(
    "MISSING_ISSUE_BODY_FILENAME", "sample-issue.j2"
)

TEMPLATES_DIRECTORY = os.getenv("TEMPLATES_DIRECTORY", "templates")

DRY_RUN = os.getenv("DRY_RUN", "True")

# SAMPLE_PRE_COMMIT_CONFIG = os.getenv(
#    "SAMPLE_PRE_COMMIT_CONFIG",
#    "sample-pre-commit-config.yaml"
# )


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
        contents = repository.get_contents(path=PRE_COMMIT_CONFIG_FILENAME)

        if contents.size <= 1:
            logging.info("pre-commit config is present but empty")
            return False

        try:
            parsed_config = yaml.safe_load(contents.content)
            if "repos" not in parsed_config:
                logging.info("invalid pre-commit config")
                return False

            if len(parsed_config["repos"]) == 0:
                logging.info("invalid pre-commit config")
                return False

        except yaml.YAMLError:
            logging.info("invalid pre-commit config")
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

    j2_environment = Environment(loader=FileSystemLoader(TEMPLATES_DIRECTORY))

    issue_template = j2_environment.get_template(MISSING_ISSUE_BODY_FILENAME)

    issue_body = issue_template.render(
        repository=repository.full_name, filename=PRE_COMMIT_CONFIG_FILENAME
    )

    if DRY_RUN.lower() == "false":
        logging.debug("attempting to create issue")
        issue = repository.create_issue(title=MISSING_ISSUE_TITLE, body=issue_body)
        logging.debug("issue created with id %i", issue.id)
        return issue.number

    logging.info("dry run, so issue not created")
    return 0


def main():
    """
    @fn main()
    @brief the main function
    """

    logging.debug('Using PAT "%s**************************"', PAT[:8])
    logging.debug('Using ORG "%s"', ORG)

    logging.basicConfig(level=logging.INFO)
    github = Github(PAT)

    for repo in github.get_organization(ORG).get_repos():
        logging.info("Checking repo '%s'", repo.name)

        if repo.archived:
            logging.info("  repo is archived; skipping")
        else:
            if has_pre_commit(repo):
                logging.info("  has pre-commit")
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


if __name__ == "__main__":
    main()
