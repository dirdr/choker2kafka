import os

from fastapi import APIRouter, HTTPException, Request
from psycopg import Error

from sentinel.connections import MissingConfiguration

router = APIRouter(prefix="/api", tags=["demo"])


@router.get("/demo")
def status(request: Request) -> dict:
    try:
        with request.app.state.repository.connection() as connection:
            reset = connection.execute(
                "SELECT * FROM sentinel.demo_resets ORDER BY completed_at DESC LIMIT 1"
            ).fetchone()
            counts = connection.execute(
                "SELECT (SELECT count(*) FROM sentinel.incidents WHERE status = 'open') AS open_incidents, (SELECT count(*) FROM sentinel.investigations WHERE status = 'completed') AS completed_investigations"
            ).fetchone()
        return {
            "github_configured": bool(os.getenv("GITHUB_TOKEN")),
            "last_reset": reset,
            **counts,
        }
    except Error, MissingConfiguration:
        raise HTTPException(503, "Demo state is unavailable") from None
