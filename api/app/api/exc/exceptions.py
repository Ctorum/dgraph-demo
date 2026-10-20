from http import HTTPStatus
from typing import final

from pydantic import BaseModel


class FieldError(BaseModel):
    name: str
    detail: str


@final
class APIError(Exception):
    def __init__(
        self,
        message: str,
        detail: str | None = None,
        status_code: int = HTTPStatus.BAD_REQUEST,
        fields: list[FieldError] | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.detail = detail
        self.status_code = status_code
        self.fields = fields or []

    def to_dict(self):
        return {
            "message": self.message,
            "detail": self.detail,
            "fields": [field.model_dump() for field in self.fields],
            "status_code": self.status_code,
        }


def does_not_exist(obj: str = "Object") -> APIError:
    return APIError(
        message=f"{obj} not found",
        status_code=HTTPStatus.NOT_FOUND,
    )


def unexpected_error(detail: str | None = None) -> APIError:
    return APIError(
        message="An unexpected error occurred, talk to the tech team",
        detail=detail,
        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
    )


def validation_error(
    message: str = "Validation error",
    fields: list[FieldError] | None = None,
    detail: str | None = None,
) -> APIError:
    return APIError(
        message=message,
        detail=detail,
        status_code=HTTPStatus.UNPROCESSABLE_CONTENT,
        fields=fields,
    )


def service_unavailable(error: Exception | None = None) -> APIError:
    return APIError(
        message="Service is unavailable",
        detail=str(error),
        status_code=HTTPStatus.SERVICE_UNAVAILABLE,
    )
