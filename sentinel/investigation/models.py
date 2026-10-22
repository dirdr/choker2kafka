import json
import re
from functools import lru_cache
from time import monotonic
from urllib.request import Request, build_opener

from sentinel.connections import required
from sentinel.readiness import NoRedirects


@lru_cache(maxsize=4)
def _models(key: str, window: int) -> tuple[tuple[str, str], ...]:
    request = Request(
        "https://api.anthropic.com/v1/models?limit=100",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
    )
    with build_opener(NoRedirects()).open(request, timeout=5) as response:
        body = json.load(response)
    return tuple(
        (item["id"], item.get("display_name", item["id"]))
        for item in body["data"]
        if re.fullmatch(r"claude-[a-zA-Z0-9-]{1,120}", item.get("id", ""))
    )


def available_models() -> list[dict]:
    return [
        {"id": model_id, "name": name}
        for model_id, name in _models(
            required("ANTHROPIC_API_KEY"), int(monotonic() // 60)
        )
    ]
