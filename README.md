# Hub Updater

This is a GitHub Action that can automatically test & build the [Jina](https://github.com/jina-ai/jina) modules in your own repo.

This will automatically try to get the latest Jina release, on a regular schedule, and open (draft) PRs on your repo in order to test your modules against this version. On success, it pushes the image to your Docker registry. On failure, it opens an issue in your repo and notifies you of the problem.

**NOTE** The PRs are open in draft mode, so you are not notified by it. The PRs are closed at the end of the job (whether successful or not). 

## Usage

- Install this GH Action on your hub-type repo

A *hub-type repo* is a repository structured like the Jina AI hub repo [here]([link](https://github.com/jina-ai/jina-hub))

- Configure it with the required environment variables and settings:

Add this under `.github/workflows/update-test-jina.yml`:

```yaml
name: Update hub

on:
  workflow_dispatch:
  schedule:
    - cron: '0 0 * * *'  # every day at midnight

jobs:
  update-jina-hub:
    runs-on: ubuntu-latest
    timeout-minutes: 600
    steps:
      - name: Jina Hub Updater
        uses: jina-ai/action-hub-updater@master
        with:
          GITHUB_TOKEN: ${{ secrets.YOUR_SECRETS }}
          TAG_IN_ISSUES: 'your_username'
          MODULES_REPO: 'your-organization/hub-type-repo'

```

This will periodically (at midnight) check whether there is a new Jina release that you haven't tested your modules against yet. It will open draft PRs in the repo, that will trigger the Hub Builder Action (see below). The PRs will trigger the build, test, deployment. If the process fails, an issue will be opened in the repo and the user will be tagged. If all is OK, nothing to do: your new image will be pushed to your Dockerhub, using the naming convention `folder.subfolder.modulename:{module version}-{jina version}`. Ex. `pod.crafter.dummyhubexecutor:0.1.0-0.8.1`.

- Install the [Jina Hub Builder GH Action](https://github.com/jina-ai/action-hub-builder) on the same repo.

Configure it, by adding the following under `.github/workflows/ci.yml`:

```yaml
name: CI

on: [pull_request]

jobs:
  hub-build-test:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v2
      - name: Jina Hub Image Builder
        uses: jina-ai/action-hub-builder@master
        with:
          push: true
          dockerhub_username: ${{ secrets.dockerhub_username }}
          dockerhub_password: ${{ secrets.dockerhub_password }}
```

See the **README** of Hub Builder for more info, [here](https://github.com/jina-ai/hub-builder/blob/master/README.md)

This will trigger a build, test, and (possibly) push of the module that's been affected by a given PR. The PRs are open in draft mode and closed at the end of the process.

## NOTES

- Modules for which there is an open issue will be ignored (with the name `fix module ModuleName`). This applies to newer versions of Jina releases. You will need to fix older versions, close the issue, and then there can be a new attempt on a **new** version of Jina. 
- Do **NOT** permanently delete the PRs. They are used in order to track which versions of Jina have been tested on which modules. (In fact, by default, GitHub doesn't allow you, due to the principle of "transparency of work").
