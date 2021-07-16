import os
import re

import click
from git import Repo, BadName
from github import Github, UnknownObjectException

client = Github(os.getenv("GITHUB_TOKEN"))


def get_pr_info(pr_url):
    if not pr_url:
        raise click.exceptions.ClickException("Invalid PR URL")

    regex = r"https://(api\.|)github\.com/(repos\/|)(?P<repo>.*?)/pulls?/(?P<pull_id>\d+)"
    matches = re.match(regex, pr_url)

    try:
        matches = matches.groupdict()
        repo = client.get_repo(matches.get("repo"))
        pull_request = repo.get_pull(int(matches.get("pull_id")))

        return dict(
            base_branch=pull_request.base.ref,
            base_sha=pull_request.base.sha,
            base_repo=pull_request.base.repo.clone_url,
            head_branch=pull_request.head.ref,
            head_sha=pull_request.head.sha,
            head_repo=pull_request.head.repo.clone_url,
            is_mergeable=not pull_request.merged and pull_request.mergeable,
        )
    except UnknownObjectException as e:
        click.secho("Failed to locate given Pull request", fg="yellow")

    return {}


def get_git_info(work_dir, variables):
    repo = Repo(work_dir)

    current_commit_tag = next(filter(lambda x: x.commit == repo.head.commit, repo.tags), "")
    previous_tag = None
    tags = list(filter(lambda x: x.commit != repo.head.commit, repo.tags))
    if len(tags) > 2:
        previous_tag = tags[-1]

    # check deployments if there is no tag
    previous_deployment_sha = None
    remote_repo = client.get_repo(os.getenv("GITHUB_REPOSITORY"))
    deployments = remote_repo.get_deployments(environment=os.getenv("STAGE"))
    deployments = deployments[:10]  # limit to last 10 deployments
    for i in deployments:
        for x in remote_repo.get_deployment(i.id).get_statuses():
            if remote_repo.get_deployment(i.id).get_status(x.id).state == "success" and not previous_deployment_sha:
                previous_deployment_sha = remote_repo.get_deployment(i.id).sha
    # We didn't find any deployments or there is none? use first git commit instead!
    if previous_deployment_sha is None:
        commits_in_master = repo.iter_commits(rev=repo.branches.master)
        previous_deployment_sha = list(commits_in_master)[-1].hexsha

    if "head_branch" in variables:
        deployment_ref = variables.get("head_branch")
    elif current_commit_tag:
        deployment_ref = f"refs/tags/{current_commit_tag}"
    else:
        deployment_ref = os.getenv("GITHUB_REF")

    return dict(
        deployment_ref=deployment_ref,
        current_commit_tag=current_commit_tag,
        previous_tag=str(previous_tag),
        previous_tag_sha=str(previous_tag.tag) if previous_tag else "",
        previous_deployment_sha=str(previous_deployment_sha),
    )


@click.group()
def run():
    pass


@run.command()
@click.option("--pr", default=os.getenv("GITHUB_PR_URL"))
@click.option("--work-dir", default=os.getcwd())
@click.option("--debug", is_flag=True)
def info(pr, debug, work_dir):
    variables = {}
    if pr:
        variables.update(get_pr_info(pr))

    variables.update(get_git_info(work_dir, variables))

    for k, v in variables.items():
        if debug:
            click.secho(f"{k}::{v}", fg="green")

        click.echo(f"::set-output name={k}::{v if type(v) != bool else str(v).lower()}")


@run.command(name="has-changes")
@click.option("--debug", is_flag=True)
@click.option("--work-dir", default=os.getcwd())
def has_changes(work_dir, debug):
    repo = Repo(work_dir)
    if debug:
        click.secho(f"has_changes::{repo.is_dirty()}", fg="green")
    click.echo(f"::set-output name=has_changes::{'true' if repo.is_dirty() else 'false'}")


@run.command(name="is-behind")
@click.option("--pr", default=os.getenv("GITHUB_PR_URL"), required=True)
@click.option("--work-dir", default=os.getcwd())
@click.option("--debug", is_flag=True)
def is_behind(pr, work_dir, debug):
    pr = get_pr_info(pr)

    repo = Repo(work_dir)
    is_behind = False
    try:
        commits = list(repo.iter_commits(f"origin/{pr['head_branch']}..origin/{pr['base_branch']}"))
        is_behind = len(commits) > 0
        if debug:
            click.secho(f"is_behind::{is_behind}", fg="green")
    except BadName as e:
        pass

    click.echo(f"::set-output name=is_behind::{str(is_behind).lower()}")
