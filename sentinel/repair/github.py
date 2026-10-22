import base64
import json
from urllib.parse import urlencode

from sentinel.github import GitHubClient, GitHubError
from sentinel.producer.domain import SourceFile
from sentinel.repair.domain import RepairBlocked


def open_pull_request(client: GitHubClient, repair: dict) -> dict:
    proposal = repair["proposal"]
    branch = repair["branch"]
    if (
        client.repository != repair["repository"]
        or client.branch != repair["base_branch"]
    ):
        raise RepairBlocked("repository_changed")
    pulls = client.request(
        "GET",
        "/pulls?"
        + urlencode(
            {
                "head": f"{client.repository.split('/')[0]}:{branch}",
                "base": client.branch,
                "state": "all",
            }
        ),
    )
    if pulls:
        return {
            "number": pulls[0]["number"],
            "html_url": pulls[0]["html_url"],
            "file_sha": client.file(branch)["sha"],
        }
    head = client.head()
    source = SourceFile.github(
        client.file(head), head, client.repository, client.branch
    )
    if (
        source.file_sha != proposal["expected_file_sha"]
        or source.configuration.model_dump(mode="json") != proposal["before"]
    ):
        raise RepairBlocked("source_changed")
    try:
        client.head(branch)
    except GitHubError as error:
        if error.status != 404:
            raise
        try:
            client.request(
                "POST", "/git/refs", {"ref": f"refs/heads/{branch}", "sha": head}
            )
        except GitHubError as conflict:
            if conflict.status != 422:
                raise
            client.head(branch)
    branch_source = SourceFile.github(
        client.file(branch), head, client.repository, branch
    )
    if branch_source.configuration.model_dump(mode="json") == proposal["after"]:
        file_sha = branch_source.file_sha
    elif branch_source.file_sha == proposal["expected_file_sha"]:
        content = (json.dumps(proposal["after"], indent=2) + "\n").encode()
        result = client.request(
            "PUT",
            "/contents/producer/config.json",
            {
                "message": f"fix: align producer with contract for incident {repair['incident_id']}",
                "content": base64.b64encode(content).decode(),
                "sha": branch_source.file_sha,
                "branch": branch,
            },
        )
        file_sha = result["content"]["sha"]
    else:
        raise RepairBlocked("repair_branch_changed")
    body = (
        f"Producer revision {proposal['expected_revision']} violates its captured contract. "
        f"This PR updates only `producer/config.json`, changing `event_time_unit` "
        f"from `{proposal['before']['event_time_unit']}` to `{proposal['after']['event_time_unit']}`.\n\n"
        f"Incident: `{repair['incident_id']}`\n\n"
        "Evidence references:\n"
        + "\n".join(f"- `{item}`" for item in proposal["evidence_ids"])
        + "\n\nValidation: the target unit comes from the frozen contract. Sentinel will verify fresh records after merge before resolving the incident."
    )
    pr = client.request(
        "POST",
        "/pulls",
        {
            "title": f"fix: restore producer contract for incident {str(repair['incident_id'])[:8]}",
            "head": branch,
            "base": client.branch,
            "body": body,
        },
    )
    return {"number": pr["number"], "html_url": pr["html_url"], "file_sha": file_sha}
