import os
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from psycopg import Error as PostgresError

from sentinel.connections import MissingConfiguration
from sentinel.detection.postgres import DetectionRepository

router = APIRouter(prefix="/api", tags=["detection"])


def repository(request: Request) -> DetectionRepository:
    instance = getattr(request.app.state, "detection_repository", None)
    if instance is None:
        raise HTTPException(503, "Detection is not initialized")
    return instance


Repository = Annotated[DetectionRepository, Depends(repository)]
Limit = Annotated[int, Query(ge=1, le=100)]


def topic() -> str:
    return os.getenv("KAFKA_TOPIC", "orders")


@router.get("/contracts")
def contracts(repository: Repository, limit: Limit = 20) -> list[dict]:
    try:
        return [row["definition"] for row in repository.contracts(topic(), limit)]
    except PostgresError, MissingConfiguration:
        raise HTTPException(503, "Detection storage is unavailable") from None


@router.get("/detection")
def detection_status(request: Request, repository: Repository) -> dict:
    worker = getattr(request.app.state, "detection_worker", None)
    state = worker.status() if worker else {"worker": "disabled", "last_error": None}
    try:
        checks = repository.status(topic())
        return {**state, "topic": topic(), "checks": checks}
    except PostgresError, MissingConfiguration:
        raise HTTPException(503, "Detection storage is unavailable") from None


@router.get("/incidents")
def incidents(
    repository: Repository,
    limit: Limit = 20,
    status: Literal["open", "resolved"] | None = None,
) -> list[dict]:
    try:
        return repository.incidents(limit, status)
    except PostgresError, MissingConfiguration:
        raise HTTPException(503, "Detection storage is unavailable") from None


@router.get("/incidents/{incident_id}")
def incident(incident_id: UUID, repository: Repository) -> dict:
    try:
        result = repository.incident(incident_id)
    except PostgresError, MissingConfiguration:
        raise HTTPException(503, "Detection storage is unavailable") from None
    if result is None:
        raise HTTPException(404, "Incident not found")
    return result


@router.get("/incidents/{incident_id}/evidence")
def evidence(incident_id: UUID, repository: Repository) -> dict:
    try:
        result = repository.evidence(incident_id)
    except PostgresError, MissingConfiguration:
        raise HTTPException(503, "Detection storage is unavailable") from None
    if result is None:
        raise HTTPException(404, "Incident evidence not found")
    return result
