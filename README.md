# Hub Updater

This is a GitHub Action that can automatically test & build the Jina modules in your own repo.

This will automatically try to get the latest Jina release, on a regular schedule, and open (draft) PRs on your repo in order to test your modules against this version. On success, it pushes the image to your Docker registry. On failure, it opens an issue in your repo and notifies you of the problem.

**NOTE** The PRs are open in draft mode, so you are not notified by it. The PRs are closed at the end of the job (whether successful or not). 

## Usage

- Install this GH Action on your hub-type repo

A *hub-type repo* is a repository structured like the Jina AI hub repo [here]([link](https://github.com/jina-ai/jina-hub))

- Configure it with the required environment variables
- Install the Jina Hub Builder GH Action on the same repo

