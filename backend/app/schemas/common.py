from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[dict] | None = None


class Envelope(BaseModel, Generic[T]):
    """Every response uses this shape (docs/API_CONTRACT.md)."""

    success: bool = True
    data: T | None = None
    error: ErrorBody | None = None


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


def ok(data):
    return {"success": True, "data": data, "error": None}
