from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from psycopg import Error as PostgresError
from pydantic import BaseModel, ConfigDict, Field

from sentinel.connections import MissingConfiguration
from sentinel.investigation.postgres import (
    InvestigationConflict,
    InvestigationRepository,
)
from sentinel.investigation.settings import (
    AGENT_VERSION,
    configured_model,
    deadline_seconds,
    token_limit,
)
from sentinel.stream.web import operator

router = APIRouter(prefix="/api", tags=["investigation"])


def repository(request: Request) -> InvestigationRepository:
    instance = getattr(request.app.state, "investigation_repository", None)
    if instance is None:
        raise HTTPException(503, "Investigation is not initialized")
    return instance


Repository = Annotated[InvestigationRepository, Depends(repository)]


@router.get("/investigation")
def status(request: Request) -> dict:
    worker = getattr(request.app.state, "investigation_worker", None)
    state = worker.status() if worker else {"worker": "disabled", "last_error": None}
    try:
        return {
            **state,
            "provider": "anthropic",
            "model_id": configured_model(),
            "agent_version": AGENT_VERSION,
            "token_limit": token_limit(),
            "tool_call_limit": 10,
            "deadline_seconds": deadline_seconds(),
        }
    except ValueError:
        raise HTTPException(
            503, "Investigation model configuration is invalid"
        ) from None


@router.get("/incidents/{incident_id}/investigations")
def investigations(incident_id: UUID, repository: Repository) -> list[dict]:
    try:
        return repository.list(incident_id)
    except PostgresError, MissingConfiguration:
        raise HTTPException(503, "Investigation storage is unavailable") from None


@router.get("/investigations/{investigation_id}")
def investigation(
    investigation_id: UUID,
    repository: Repository,
    include_activity_bodies: bool = False,
) -> dict:
    try:
        result = repository.detail(investigation_id, include_activity_bodies)
    except PostgresError, MissingConfiguration:
        raise HTTPException(503, "Investigation storage is unavailable") from None
    if result is None:
        raise HTTPException(404, "Investigation not found")
    return result


class RetryBudget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token_limit: int | None = Field(default=None, ge=4000, le=100000, strict=True)
    deadline_seconds: int | None = Field(default=None, ge=30, le=300, strict=True)


@router.post(
    "/incidents/{incident_id}/investigations/retry",
    status_code=202,
    dependencies=[Depends(operator)],
)
def retry(
    incident_id: UUID,
    repository: Repository,
    request: Request,
    budget: RetryBudget | None = None,
) -> dict:
    if not getattr(request.app.state, "investigation_worker", None):
        raise HTTPException(503, "Investigation worker is disabled")
    try:
        options = budget or RetryBudget()
        result = repository.retry(
            incident_id,
            configured_model(),
            options.token_limit if options.token_limit is not None else token_limit(),
            options.deadline_seconds
            if options.deadline_seconds is not None
            else deadline_seconds(),
        )
    except InvestigationConflict:
        raise HTTPException(
            409, "Only a failed investigation of an open incident can be retried"
        ) from None
    except PostgresError, MissingConfiguration, ValueError:
        raise HTTPException(
            503, "Investigation storage or configuration is unavailable"
        ) from None
    if result is None:
        raise HTTPException(404, "Incident not found")
    return result
