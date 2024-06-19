# pre-commit-checker

This is a tool to determine if a GitHub organization's repositories
have `.pre-commit-config.yaml` files or not; if they do not, it will
check to see if an issue exists to create that file.

## Background

My team became privy to a situation where several secrets
(credentials, API tokens, etc.) were committed to a repository.
[MegaLinter](https://megalinter.io) was run on the repository and
happened to detect these secrets that, while no longer active,
were artifacts from previous development iterations.  We were
tasked to looking into the situation and provide advice and
guidance about how to prevent situations like these from
happening again.

In addition to running MegaLinter whenever Pull Requests (PRs)
were submitted, we recommended a layer of protection before
commits were created or pushed upstream.

The [pre-commit](https://pre-commit.com/) tool allows us to
configure steps to run before commits are created.  These
steps use git's
[hooks](https://git-scm.com/book/en/v2/Customizing-Git-Git-Hooks)
functionality to invoke tools to protect our developers:

* [detect private key](https://github.com/pre-commit/pre-commit-hooks)
* [detect AWS credentials](https://github.com/pre-commit/pre-commit-hooks)
* [gitleaks](https://github.com/zricethezav/gitleaks)
* [detect secrets](https://github.com/Yelp/detect-secrets)

## This Tool

From an administrative perspective, we didn't -- and can't -- have
a mechanism to determine if an individual developer did or did not
use pre-commit.  Similarly, we couldn't force individual
developers to install or setup pre-commit on a system or
repository basis.

What did know was that if a repository did not have a pre-commit
configuration, we know that they do not have pre-commit protection
in place.

So, this tool scans through all of the repositories in a GitHub
organization and attempts to retrieve their pre-commit configuration
files.  For each repository, if there is no pre-commit configuration
file, we create an issue in the repository.  If there is a pre-commit
file but that file is empty or invalid or doesn't have the elements
pre-commit requires, we create an issue in the repository.

The issues this tool creates are based on a
[Jinja2](https://jinja.palletsprojects.com/en/2.10.x/) template.
This template describes the background, provides instructions on
how to use pre-commit, and includes a sample pre-commit configuration
file that the developer can store in `.pre-commit-config.yaml` in
the repository.

### Configuring the Tool

The tool is configured using environment variables and/or a `.env`
file.  This method was selected so that the tool could be run
in a containerized environment, as a CI/CD workflow, as a
scheduled process, etc..

The tool does not require disk access -- it can run in an
ephermal, immutable exection environment.

#### Environment Variables

Required values:

* **PAT**: a Personal Access Token for interacting with GitHub to
  list the repositories in an organization, extract and validate
  the contents of any `.pre-commit-config.yaml` files, and
  create issues on the repositories that don't meet the tool's
  requirements.
* **ORG**: the GitHub Organization to scan for repos to check

Optional values:

* **MISSING_ISSUE_TITLE**: the title of issues to create; if this is
  changed after running, new issues may be created for
  non-compliant repositories (i.e., it looks to see if issues
  exist with this title before creating new issues); the
  default is `Missing pre-commit configuration`
* **OPEN_ISSUE_BODY_FILENAME**: the filename for the Jinja2
  template used to create new issues; the default is
  `open-issue.j2`
* **CLOSE_ISSUE_BODY_FILENAME**: the filename for the Jinja2
  template used for the closing comment on an issue; the
  default is `close-issue.j2`
* **TEMPLATES_DIRECTORY**: this is the directory where the Jinja2
  templates are stored; the default is `templates/`
* **API_URL**: the base URL to a GitHub API to query; if
  supporting a GitHub Enterprise (GHE) instance, change this
  variable to point to the instance; otherwise, the default,
  `https://api.github.com` is sufficient for repositories
  hosted on GitHub.com.
* **DRY_RUN**: This must be set to 'False' to actually create issues
* **LOG_LEVEL**: the threshold for displaying log messages
  10 = Debug, 20 = Info (default), 30 = Warning, 40 = Error, 50 = Critcal
