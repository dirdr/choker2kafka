import hashlib
import hmac
import os
import secrets
from time import time
from urllib.parse import urlsplit

from fastapi import HTTPException, Request

from sentinel.connections import required


def settings_enabled() -> bool:
    return bool(os.getenv("OPERATOR_TOKEN", "").strip())


def signature(payload: str, host: str) -> str:
    return hmac.new(
        required("OPERATOR_TOKEN").encode(),
        f"{host}:{payload}".encode(),
        hashlib.sha256,
    ).hexdigest()


def browser_token(request: Request) -> str | None:
    if not settings_enabled():
        return None
    payload = f"{int(time())}.{secrets.token_urlsafe(24)}"
    return f"{payload}.{signature(payload, request.url.netloc)}"


def settings_access(request: Request) -> None:
    if not settings_enabled():
        raise HTTPException(503, "Configure OPERATOR_TOKEN to enable settings changes")
    origin = urlsplit(request.headers.get("origin", ""))
    if (
        origin.scheme not in {"http", "https"}
        or origin.netloc != request.url.netloc
        or request.headers.get("sec-fetch-site") != "same-origin"
    ):
        raise HTTPException(403, "Settings changes must come from this application")
    token = request.headers.get("x-sentinel-csrf", "")
    try:
        issued, nonce, digest = token.split(".")
        age = time() - int(issued)
        valid = (
            0 <= age <= 3600
            and len(nonce) == 32
            and hmac.compare_digest(
                digest, signature(f"{issued}.{nonce}", request.url.netloc)
            )
        )
    except ValueError:
        valid = False
    if not valid:
        raise HTTPException(403, "Reopen investigator settings before saving")
