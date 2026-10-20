from pydantic import BaseModel, Field


class BaseResponseSchema[T](BaseModel):
    """Base response schema for API responses."""

    status: int = 200
    message: str
    data: T


class FieldErrorSchema(BaseModel):
    """Schema for field-level errors."""

    name: str = Field(..., description="The name of the field with the error")
    detail: str = Field(..., description="Details about the error")


class ErrorResponseSchema(BaseModel):
    """Schema for error responses."""

    message: str = Field(..., description="Error message")
    detail: str | None = Field(None, description="Additional error details")
    fields: list[FieldErrorSchema] = Field(
        default_factory=list, description="Field-level errors"
    )
    status_code: int = Field(..., description="HTTP status code")
