from typing import Generic, TypeVar, List
from pydantic import BaseModel, Field
from app.services.state_machine import JobStatus, JobPriority, AttemptOutcome

T = TypeVar("T")


class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1, description="Page number, 1-indexed")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page")


class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int = Field(ge=0, description="Total count of matching items")
    page: int = Field(ge=1, description="Current page number")
    page_size: int = Field(ge=1, description="Number of items per page")
    pages: int = Field(ge=0, description="Total number of available pages")


__all__ = [
    "JobStatus",
    "JobPriority",
    "AttemptOutcome",
    "PaginationParams",
    "PaginatedResponse",
]
