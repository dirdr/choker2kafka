import os
import re

from pydantic import BaseModel, ConfigDict, Field

MODEL_ID = "claude-haiku-4-5-20251001"
AGENT_VERSION = "investigator-v2"


def configured_model() -> str:
    value = os.getenv("ANTHROPIC_MODEL", MODEL_ID).strip()
    if not re.fullmatch(r"claude-[a-zA-Z0-9-]{1,120}", value):
        raise ValueError("ANTHROPIC_MODEL must be a Claude model ID")
    return value


def token_limit() -> int:
    value = int(os.getenv("INVESTIGATION_TOKEN_LIMIT", "50000"))
    if not 4000 <= value <= 100000:
        raise ValueError("INVESTIGATION_TOKEN_LIMIT must be between 4000 and 100000")
    return value


def deadline_seconds() -> int:
    value = int(os.getenv("INVESTIGATION_DEADLINE_SECONDS", "120"))
    if not 30 <= value <= 300:
        raise ValueError("INVESTIGATION_DEADLINE_SECONDS must be between 30 and 300")
    return value


class SettingsConflict(ValueError):
    pass


class SettingsChange(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_revision: int = Field(ge=0, le=2**63 - 2, strict=True)
    model_id: str = Field(pattern=r"^claude-[a-zA-Z0-9-]{1,120}$", strict=True)
    token_limit: int = Field(ge=4000, le=100000, strict=True)
