import os
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from psycopg import Error as PostgresError

from sentinel.connections import MissingConfiguration
from sentinel.stream.domain import (
    ConfigurationChange,
    ProducerConfiguration,
    RevisionConflict,
)
from sentinel.stream.postgres import PostgresRepository

router = APIRouter(prefix="/api", tags=["stream"])
bearer = HTTPBearer(auto_error=False)


def repository(request: Request) -> PostgresRepository:
    instance = getattr(request.app.state, "repository", None)
    if instance is None:
        raise HTTPException(503, "Stream is not initialized")
    return instance


Repository = Annotated[PostgresRepository, Depends(repository)]


def operator(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    token = os.getenv("OPERATOR_TOKEN", "")
    if not token:
        raise HTTPException(
            503, "Configure OPERATOR_TOKEN to enable configuration changes"
        )
    if credentials is None or not secrets.compare_digest(
        credentials.credentials.encode(), token.encode()
    ):
        raise HTTPException(
            401,
            "Operator authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.get("/stream")
def stream_status(request: Request, repository: Repository) -> dict:
    worker = getattr(request.app.state, "stream_worker", None)
    state = worker.status() if worker else {"worker": "disabled", "last_error": None}
    try:
        return {**state, **repository.status()}
    except PostgresError, MissingConfiguration:
        raise HTTPException(503, "Stream storage is unavailable") from None


@router.get("/events")
def recent_events(
    repository: Repository, limit: Annotated[int, Query(ge=1, le=100)] = 20
) -> list[dict]:
    try:
        return repository.recent_events(limit)
    except PostgresError, MissingConfiguration:
        raise HTTPException(503, "Stream storage is unavailable") from None


@router.get("/producer/configuration")
def producer_configuration(repository: Repository) -> ProducerConfiguration:
    try:
        return repository.configuration()
    except PostgresError, MissingConfiguration:
        raise HTTPException(503, "Stream storage is unavailable") from None


@router.get("/producer/configuration/history")
def configuration_history(repository: Repository) -> list[dict]:
    try:
        return repository.configuration_history()
    except PostgresError, MissingConfiguration:
        raise HTTPException(503, "Stream storage is unavailable") from None


@router.patch("/producer/configuration", dependencies=[Depends(operator)])
def change_configuration(
    change: ConfigurationChange, repository: Repository
) -> ProducerConfiguration:
    try:
        return repository.change_configuration(change)
    except RevisionConflict:
        raise HTTPException(
            409, "Producer configuration revision has changed; reload before retrying"
        ) from None
    except PostgresError, MissingConfiguration:
        raise HTTPException(503, "Stream storage is unavailable") from None
