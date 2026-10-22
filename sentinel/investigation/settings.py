import os
import re

MODEL_ID = "claude-haiku-4-5-20251001"
AGENT_VERSION = "investigator-v2"


def configured_model() -> str:
    value = os.getenv("ANTHROPIC_MODEL", MODEL_ID).strip()
    if not re.fullmatch(r"claude-[a-zA-Z0-9-]{1,120}", value):
        raise ValueError("ANTHROPIC_MODEL must be a Claude model ID")
    return value


def token_limit() -> int:
    value = int(os.getenv("INVESTIGATION_TOKEN_LIMIT", "20000"))
    if not 4000 <= value <= 100000:
        raise ValueError("INVESTIGATION_TOKEN_LIMIT must be between 4000 and 100000")
    return value
