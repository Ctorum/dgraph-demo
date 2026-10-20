from fastapi import Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .exceptions import (
    APIError,
    FieldError,
    validation_error,
)


def _to_response(error: APIError) -> Response:
    return JSONResponse(
        error.to_dict(),
        status_code=error.status_code,
        headers={"X-Error": error.message},
    )


async def pydantic_validation_error_handler(
    _: Request, exc: RequestValidationError
) -> Response:
    return _to_response(
        validation_error(
            message="Data validation failed",
            fields=[
                FieldError(
                    name=".".join(str(loc) for loc in err["loc"]),
                    detail=err["msg"],
                )
                for err in exc.errors()
            ],
            detail=f"{len(exc.errors())} validation error(s)",
        )
    )


async def api_error_handler(_: Request, exc: APIError) -> Response:
    return _to_response(exc)
