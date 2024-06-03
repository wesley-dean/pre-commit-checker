#!/usr/bin/env python

import logging
import os

from github import Github
from github.GithubException import UnknownObjectException
from github import Auth
from dotenv import load_dotenv

MISSING_ISSUE_TITLE = "Missing pre-commit configuration"

def has_pre_commit_issue(repository):
    for issue in repository.get_issues(state = 'open'):
        if issue.title == MISSING_ISSUE_TITLE:
            return True

    return False

def has_pre_commit(repository):

    try:
        pre_commit_content = repository.get_contents(path='.pre-commit-config.yaml')
    except UnknownObjectException:
#    except:
        return False
    else:
        return True


def main():

    logging.basicConfig(level=logging.INFO)
    load_dotenv()

    pat = os.environ["PAT"]
    org = os.environ["ORG"]

    logging.debug('Using PAT "%s**************************"', pat[:8])
    logging.debug('Using ORG "%s"', org)

    auth = Auth.Token(pat)

    g = Github(auth=auth)

    for repo in g.get_organization(org).get_repos():
        if repo.archived:
            next

        print(repo.name)

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

