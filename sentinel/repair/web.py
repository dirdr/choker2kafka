from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from psycopg import Error

from sentinel.connections import MissingConfiguration
from sentinel.repair.postgres import RepairRepository

router = APIRouter(prefix="/api", tags=["repair"])


@router.get("/repair")
def status(request: Request) -> dict:
    worker = getattr(request.app.state, "repair_worker", None)
    return worker.status() if worker else {"worker": "disabled", "last_error": None}


@router.get("/incidents/{incident_id}/repair")
def repair(incident_id: UUID, request: Request) -> dict:
    try:
        result = RepairRepository(request.app.state.repository).detail(incident_id)
    except Error, MissingConfiguration:
        raise HTTPException(503, "Repair storage is unavailable") from None
    return result or {"status": "awaiting_supported_finding"}
