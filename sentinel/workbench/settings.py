from urllib.error import URLError

from fastapi import APIRouter, Depends, Request, Response

from sentinel.connections import MissingConfiguration
from sentinel.investigation.models import available_models
from sentinel.investigation.settings import SettingsChange
from sentinel.investigation.web import Repository, settings, update_settings
from sentinel.workbench.access import browser_token, settings_access, settings_enabled

router = APIRouter(prefix="/workbench/investigator", include_in_schema=False)


@router.get("/settings")
def investigator_settings(
    request: Request, response: Response, repository: Repository
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    current = settings(repository)
    try:
        models = available_models()
    except URLError, OSError, ValueError, KeyError, MissingConfiguration:
        models = []
    return {
        "settings": current,
        "models": models,
        "editable": settings_enabled(),
        "csrf_token": browser_token(request),
    }


@router.patch("/settings", dependencies=[Depends(settings_access)])
def save_settings(
    change: SettingsChange, response: Response, repository: Repository
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return update_settings(change, repository)
