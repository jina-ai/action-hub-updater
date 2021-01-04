""" Script to change versioning of files (eg. manifest.yml) for executors
[encoders, crafters, indexers, rankers, evaluators, classifiers etc.].
It also adds the required jina version.
Commits the change in the branch and raises a PR for the executor.
Then attempts to automatically merge the PRs
"""
import glob
import os
import traceback
from typing import List, Optional, Tuple, Dict
import pkg_resources

import git
import requests
import sys
import time
import semver
from github import Github, Repository
from github.Issue import Issue
from github.PullRequest import PullRequest
from ruamel.yaml import YAML

WAIT_BETWEEN_PR_CHECKS = 5 * 60
FIX_MODULE_TEMPLATE = 'fix module '
COMPARISON_TYPES = ["major", "minor", "patch"]

TAG_IN_ISSUES = os.environ.get('TAG_IN_ISSUES', '')
MODULES_REPO = os.environ.get('MODULES_REPO')
GITHUB_TOKEN = os.environ['GITHUB_TOKEN']
COMPARISON_LEVEL = os.environ['COMPARISON_LEVEL']
TEST_AGAIN = os.environ['TEST_AGAIN'] or None
if TEST_AGAIN == 'true':
    TEST_AGAIN = True
elif TEST_AGAIN == 'false':
    TEST_AGAIN = False
else:
    print(f'Error: TEST_AGAIN needs to be set. Exiting...')
    sys.exit(1)

if MODULES_REPO is None:
    print(f'Error: MODULES_REPO needs to be set. Exiting...')
    sys.exit(1)

if GITHUB_TOKEN is None:
    print(f'Error: GITHUB_TOKEN needs to be set. Exiting...')
    sys.exit(1)

if COMPARISON_LEVEL is None:
    print(f'Error: COMPARISON_LEVEL needs to be set. Exiting...')
    sys.exit(1)

if COMPARISON_LEVEL not in COMPARISON_TYPES:
    print(f'Error: COMPARISON_LEVEL needs to be one of {COMPARISON_TYPES}')
    sys.exit(1)

GITHUB_API_HEADERS = {
    f'Authorization': f'token {GITHUB_TOKEN}',
    'Accept': 'application/vnd.github.v3+json'
}

# this one has PR push access
g = Github(GITHUB_TOKEN)
print(f'rate limit status: {g.get_rate_limit()}')

yaml = YAML()


def get_pr_from_gh(pr_name, all_prs):
    """try to obtain existing open PR with name in GH"""
    prs = [
        pr for pr in all_prs
        if pr_name in pr.title
    ]
    if len(prs) > 1:
        print(f'Warning: Too many PRs matched query "{pr_name}": {[p.html_url for p in prs]}. Returning first.')
        return prs[0]
    elif len(prs) == 1:
        pr = prs[0]
        print(f'Found existing PR for {pr_name}: {pr.html_url}')
        return prs[0]
    else:
        print(f'Couldn\'t retrieve PR for module version and jina version. Will create...')
        return None


def create_pr(manifest_path, requirements_path, module, jina_core_version, hub_repo, hub_origin, gh_hub_repo, all_prs) -> Optional[PullRequest]:
    """for each module with manifest.yml attempts to open a PR for testing specific jina version returns None (if no
    need to open new PR), old PR (if found and 'open'), new PR (if versions haven't been tested before)
    """
    # noinspection PyTypeChecker
    pr = None
    timestamp = time.time()
    print(f'handling {module}...')
    module_version = None
    with open(manifest_path) as fp:
        info = yaml.load(fp)
        module_version = info['version']
        # in order to trigger a PR we make a 'dummy' change to the timestamp
        info['timestamp'] = timestamp

    # means this module version + jina version has been tested before
    # NOTE: DO NOT MODIFY THIS AS IT'S NEEDED FOR SEARCHING ON GITHUB
    pr_name = f'chore: testing/building {module} ({module_version}) on new jina core: {jina_core_version}'
    if COMPARISON_LEVEL == 'major':
        version = semver.parse(jina_core_version)
        pr_name = f'chore: testing/building {module} ({module_version}) on new jina core: {version["major"]}.'
    elif COMPARISON_LEVEL == 'minor':
        version = semver.parse(jina_core_version)
        pr_name = f'chore: testing/building {module} ({module_version}) on new jina core: {version["major"]}.{version["minor"]}.'
    pr: PullRequest = get_pr_from_gh(pr_name, all_prs)
    if pr:
        print(
            f'Warning: module {module} has already been tested on {module_version} with jina {jina_core_version}. '
            f'Skipping...')
        if pr.state == 'open':
            # something must've stopped us from closing it
            # make sure we close it
            print(f'PR found open for {module} on Jina core v{jina_core_version}. Will handle now...')
            return pr
        else:
            return None

    with open(manifest_path, 'w') as fp:
        yaml.dump(info, fp)

    if os.path.exists(requirements_path):
        new_requirements = []
        update = False
        with open(requirements_path, 'r') as fp:
            requirements = pkg_resources.parse_requirements(fp)
            for req in requirements:
                if 'jina' in str(req):
                    update = True
                    new_requirements.append(f'jina=={jina_core_version}')
                else:
                    new_requirements.append(str(req))

        if update:
            with open(requirements_path, 'w') as fp:
                fp.write('\n'.join(new_requirements))

    br_name = ''
    try:
        print('preparing the branch ...')
        br_name = f'chore-{module.lower()}-{module_version}-core-{jina_core_version.replace(".", "-")}'
        # delete any existing branch if exists
        # if we don't find the PR (above), then it must've been
        # renamed (for a good reason)
        delete_remote_branch(br_name, expect_exists=False)
        new_branch = hub_repo.create_head(br_name)
        new_branch.checkout()

        print(f'bumping version for timestamp {timestamp} and committing to {new_branch}...')
        hub_repo.git.add(update=True)
        # NOTE limited to 72 characters by commit lint
        hub_repo.index.commit(f'chore: bump {module}')
        hub_repo.git.push('--set-upstream', hub_origin, hub_repo.head.ref)

        print('making a PR ...')
        body_string = f'Due to the release of jina core v{jina_core_version}, this draft PR is created in order to ' \
                      f'trigger an automatic build & push of the module '

        pr = gh_hub_repo.create_pull(
            title=pr_name,
            body=body_string,
            head=br_name,
            base='master',
            draft=True
        )
    except Exception:
        raise
    finally:
        hub_repo.git.checkout('master')
        if br_name:
            hub_repo.delete_head(br_name, force=True)

    return pr


def all_checks_passed(runs: Optional[List[Dict]]) -> Optional[bool]:
    """
    check whether all checks from a PR head ref have completed and passed
    """
    if runs is None:
        return None
    for c in runs:
        if c['status'] == 'completed':
            if c['conclusion'] == 'failure':
                return False
        else:
            return None
    return True


def get_checks_for_pr(sha) -> Optional[List[Dict]]:
    result = requests.get(
        f'https://api.github.com/repos/{MODULES_REPO}/commits/{sha}/check-runs',
        headers=GITHUB_API_HEADERS
    )
    checks = result.json()
    if 'check_runs' not in checks.keys():
        print(f'Warning: "check_runs" not in PR JSON from Github API. Will retry...')
        return None
    pr_checks = checks['check_runs']
    print(
        f'Got {len(pr_checks)} runs to check for PR: \n{[(r["name"], r["status"], r["conclusion"]) for r in pr_checks]}')
    return pr_checks


def open_issue(pr, pr_checks, hub_repo: Repository, module, jina_core_version):
    """opens an issue for the PR with the failed checks (if not already open)"""
    issue_name = f'{FIX_MODULE_TEMPLATE}{module}'
    existing_issue_for_pr = [
        i for i in list(hub_repo.get_issues(state='open'))
        if i.title == issue_name
    ]
    if len(existing_issue_for_pr) > 0:
        print(f'Found existing issue: {existing_issue_for_pr}')
        return existing_issue_for_pr[0]
    else:
        # open the issue
        body = f"""
**[This is an automated issue opened as part of the hub modules update GH action. DO NOT EDIT THIS DESCRIPTION]**

Could not build module {module} for Jina core version {jina_core_version} because some of the checks failed:

```
{[(c['name'], c['status'], c['conclusion']) for c in pr_checks]}
```

See {pr.html_url} for more info. {TAG_IN_ISSUES}
"""
        issue = hub_repo.create_issue(
            title=issue_name,
            body=body,
        )
        print(f'opened issue at {issue.html_url}')
        return issue


def delete_remote_branch(br_name, expect_exists=True):
    req = requests.delete(f'https://api.github.com/repos/{MODULES_REPO}/git/refs/heads/{br_name}',
                          headers=GITHUB_API_HEADERS)
    if req.status_code == 204:
        if expect_exists:
            print(f'branch {br_name} deleted')
        else:
            print(f'Warning: {br_name} existed and was deleted')
    elif expect_exists:
        print(f'WARNING: Output from attempting to delete branch. code {req.status_code}, json: {req.json()}')
    return


def close_related_issue(pr, hub_repo, module):
    issue_name = f'{FIX_MODULE_TEMPLATE}{module}'
    existing_issues_for_pr: List[Issue] = [
        i for i in list(hub_repo.get_issues(state='open'))
        if i.title == issue_name
    ]
    if len(existing_issues_for_pr) > 0:
        print(f'Found existing issue: {existing_issues_for_pr}')
        if len(existing_issues_for_pr) > 1:
            print(f'Warning: Found too many matching issues. Will close them all.')
        for i in existing_issues_for_pr:
            i.create_comment(f'Closing issue as build succeeded on PR {pr.html_url}')
            i.edit(state='closed')
    return


def handle_prs(prs_modules: List[Tuple[PullRequest, str]], hub_repo, jina_core_version):
    """
    traverses list of open PRs. Confirms whether checks have passed or not. If not, opens issues

    """
    # noinspection PyBroadException
    if len(prs_modules) == 0:
        return

    # noinspection PyBroadException
    try:
        # allow for checks to be initiated. It's not instantaneous
        print(f'waiting for 2 mins. before continuing...')
        time.sleep(120)
        new_prs = []
        while len(prs_modules) > 0:
            for i, pr_module in enumerate(prs_modules):
                print(f'rate limit status: {g.get_rate_limit()}')
                pr = None
                try:
                    pr = pr_module[0]
                    module = pr_module[1]
                    print(f'Checking PR {pr} ( {pr.html_url} )...')
                    br_name = pr.head.ref
                    last_commit = sorted(list(pr.get_commits()), key=lambda t: t.commit.author.date)[-1]
                    sha = last_commit.sha
                    pr_checks: Optional[List[Dict]] = get_checks_for_pr(sha)
                    checks_passed = all_checks_passed(pr_checks)
                    if checks_passed is None:
                        print(f'Not all checks have completed for {br_name}. Skipping and will attempt later...')
                        new_prs.append((pr, module))
                    else:
                        if checks_passed:
                            print(f'All checks completed and passed for {br_name}. Commenting and closing...')
                            pr.create_issue_comment(
                                f'Automatic build successful. Image has been built and deployed.'
                            )
                            # close any open issues related to this module using the template
                            close_related_issue(pr, hub_repo, module)
                        else:

                            print(
                                f'warning: not all checks have passed for {br_name}. '
                                f'Will open issue and abandon trying.')
                            issue = open_issue(pr, pr_checks, hub_repo, module, jina_core_version)
                            pr.create_issue_comment(
                                f'Automatic build failed in this PR and we '
                                f'have opened an issue here: {issue.html_url}. '
                                f'Closing this PR. '
                            )
                        pr.edit(state='closed')
                        delete_remote_branch(br_name, expect_exists=True)
                except Exception as e:
                    print(f'Error handling pr {pr}. Error: {repr(e)}')

            # starting the checking process again on the subset
            # of PRs that had not yet completed
            prs_modules = new_prs
            print(f'Have {len(prs_modules)} PRs left to check')
            if len(prs_modules) > 0:
                print(f'waiting for {WAIT_BETWEEN_PR_CHECKS // 60} mins. before continuing...')
                time.sleep(WAIT_BETWEEN_PR_CHECKS)
            new_prs = []
        print('Done!')
    except Exception:
        print(f'Error occurred: {traceback.format_exc()}')


def get_issues_for_modules(hub_repo: Repository):
    issues: List[Issue] = list(hub_repo.get_issues(
        state='open'
    ))
    issues = [
        i for i in issues if FIX_MODULE_TEMPLATE in i.title
    ]
    names = [
        i.title.split(FIX_MODULE_TEMPLATE)[-1]
        for i in issues
    ]
    print(f'found {len(names)} modules to be fixed: {names}')
    return names


def get_jina_version() -> str:
    """gets stable version of jina"""
    response = requests.get('https://api.jina.ai/latest').json()
    return response['version']


def main():
    modules_dir = 'hub_repo'
    hub_repo = git.Repo(modules_dir)
    hub_origin = hub_repo.remote(name='origin')
    gh_hub_repo: Repository = g.get_repo(MODULES_REPO)
    print(f'initiated modules repo: {hub_repo} with GitHub repo {gh_hub_repo} (origin: {hub_origin})')

    jina_core_version = get_jina_version()
    print(f'got jina core v: "{jina_core_version}"')

    print(f'cur. dir. is "{os.getcwd()}"')

    modules = glob.glob(f'{modules_dir}/**/manifest.yml', recursive=True)
    print(f'got {len(modules)} modules to update')

    prs: List[Tuple[PullRequest, str]] = []
    # filter those for which there is an open issue
    # template 'fix module modulename' (ex. 'fix module DeepSegmenter')
    to_be_fixed = get_issues_for_modules(gh_hub_repo)

    # traverse list of modules in jina-hub
    all_prs = list(gh_hub_repo.get_pulls(state='all'))
    for manifest_path in modules:
        print(f'rate limit status: {g.get_rate_limit()}')
        module = manifest_path.split('/')[-2]
        requirements_path = os.path.join(os.path.dirname(manifest_path), 'requirements.txt')
        if not TEST_AGAIN and module in to_be_fixed:
            print(f'skipping {module} as there is an open issue for it...')
        else:
            pr = create_pr(manifest_path, requirements_path, module, jina_core_version, hub_repo, hub_origin, gh_hub_repo, all_prs)
            if pr:
                prs.append((pr, module))

    handle_prs(prs, gh_hub_repo, jina_core_version)


if __name__ == '__main__':
    main()
