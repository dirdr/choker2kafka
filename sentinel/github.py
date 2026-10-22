import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, build_opener

from sentinel.connections import required
from sentinel.readiness import NoRedirects


class GitHubError(RuntimeError):
    def __init__(self, status: int):
        self.status = status
        super().__init__(f"GitHub request failed ({status})")


class GitHubClient:
    def __init__(self):
        self.repository = os.getenv("GITHUB_REPOSITORY", "dirdr/choker2kafka")
        self.branch = os.getenv("GITHUB_BRANCH", "main")
        if not re.fullmatch(r"[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+", self.repository):
            raise ValueError("Invalid GitHub repository")
        if not self.branch or len(self.branch) > 200:
            raise ValueError("Invalid GitHub branch")

    def request(self, method: str, path: str, body: dict | None = None):
        if not path.startswith("/"):
            raise ValueError("Invalid repository request")
        request = Request(
            f"https://api.github.com/repos/{self.repository}{path}",
            data=json.dumps(body).encode() if body is not None else None,
            method=method,
            headers={
                "Authorization": f"Bearer {required('GITHUB_TOKEN')}",
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
                "X-GitHub-Api-Version": "2026-03-10",
                "User-Agent": "Sentinel",
            },
        )
        try:
            with build_opener(NoRedirects()).open(request, timeout=8) as response:
                content = response.read(2_000_000)
                return json.loads(content) if content else None
        except HTTPError as error:
            raise GitHubError(error.code) from None
        except URLError, OSError:
            raise GitHubError(0) from None

    def head(self, branch: str | None = None) -> str:
        return self.request(
            "GET", f"/git/ref/heads/{quote(branch or self.branch, safe='')}"
        )["object"]["sha"]

    def file(self, ref: str) -> dict:
        return self.request(
            "GET", f"/contents/producer/config.json?ref={quote(ref, safe='')}"
        )
