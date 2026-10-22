from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from psycopg import Error as PostgresError

from sentinel.connections import MissingConfiguration
from sentinel.investigation.agent import MODEL_ID, token_limit
from sentinel.investigation.postgres import (
    InvestigationConflict,
    InvestigationRepository,
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
    return worker.status() if worker else {"worker": "disabled", "last_error": None}


@router.get("/incidents/{incident_id}/investigations")
def investigations(incident_id: UUID, repository: Repository) -> list[dict]:
    try:
        return repository.list(incident_id)
    except PostgresError, MissingConfiguration:
        raise HTTPException(503, "Investigation storage is unavailable") from None


@router.get("/investigations/{investigation_id}")
def investigation(investigation_id: UUID, repository: Repository) -> dict:
    try:
        result = repository.detail(investigation_id)
    except PostgresError, MissingConfiguration:
        raise HTTPException(503, "Investigation storage is unavailable") from None
    if result is None:
        raise HTTPException(404, "Investigation not found")
    return result


@router.post(
    "/incidents/{incident_id}/investigations/retry",
    status_code=202,
    dependencies=[Depends(operator)],
)
def retry(incident_id: UUID, repository: Repository, request: Request) -> dict:
    if not getattr(request.app.state, "investigation_worker", None):
        raise HTTPException(503, "Investigation worker is disabled")
    try:
        result = repository.retry(incident_id, MODEL_ID, token_limit())
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
