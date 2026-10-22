from fastapi import APIRouter, HTTPException, Request
from psycopg import Error

from sentinel.connections import MissingConfiguration
from sentinel.producer.postgres import ProducerRepository

router = APIRouter(prefix="/api", tags=["producer"])


@router.get("/producers")
def producers(request: Request) -> dict:
    worker = getattr(request.app.state, "producer_source_worker", None)
    state = worker.status() if worker else {"worker": "disabled", "last_error": None}
    try:
        return {
            **state,
            "producers": ProducerRepository(request.app.state.repository).list(),
        }
    except Error, MissingConfiguration:
        raise HTTPException(503, "Producer source is unavailable") from None
