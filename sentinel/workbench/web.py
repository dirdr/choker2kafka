from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

ROOT = Path(__file__).resolve().parent
router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=ROOT / "templates")


@router.get("/", response_class=HTMLResponse)
@router.get("/stream", response_class=HTMLResponse)
@router.get("/contracts", response_class=HTMLResponse)
@router.get("/incidents/{incident_id}", response_class=HTMLResponse)
def workbench(request: Request, incident_id: UUID | None = None):
    return templates.TemplateResponse(
        request=request,
        name="workbench.html",
        context={"incident_id": str(incident_id) if incident_id else ""},
        headers={
            "Cache-Control": "no-store",
            "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'",
            "Referrer-Policy": "same-origin",
            "X-Content-Type-Options": "nosniff",
        },
    )
