from pydantic import ValidationError
from pydantic_ai.exceptions import (
    ModelHTTPError,
    UnexpectedModelBehavior,
    UsageLimitExceeded,
)

from sentinel.investigation.domain import UnsupportedFinding


def describe_failure(error: Exception) -> tuple[str, dict]:
    if isinstance(error, UnsupportedFinding):
        return "unsupported_finding", {
            "message": "The finding could not be linked to captured evidence",
            "reason": str(error),
        }
    current = error
    seen = set()
    for _ in range(10):
        if id(current) in seen:
            break
        seen.add(id(current))
        if isinstance(current, ValidationError):
            return "invalid_model_output", {
                "message": "The model returned a finding that did not match the required format",
                "fields": [
                    {"path": ".".join(map(str, item["loc"])), "type": item["type"]}
                    for item in current.errors(
                        include_input=False, include_context=False, include_url=False
                    )[:20]
                ],
            }
        current = current.__cause__ or current.__context__
        if current is None:
            break
    if isinstance(error, UsageLimitExceeded):
        return "usage_limit_exceeded", {
            "message": "The investigation reached its token, request or tool-call allowance"
        }
    if isinstance(error, TimeoutError):
        return "deadline_exceeded", {
            "message": "The investigation exceeded its configured deadline"
        }
    if isinstance(error, ModelHTTPError):
        return "model_http_error", {
            "message": "The model provider rejected a request",
            "status_code": error.status_code,
        }
    if isinstance(error, UnexpectedModelBehavior):
        return "invalid_model_response", {
            "message": "The model did not return a usable structured finding"
        }
    return type(error).__name__, {
        "message": "The investigation failed; inspect worker logs using the error type"
    }
