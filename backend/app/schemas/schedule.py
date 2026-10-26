import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from zoneinfo import ZoneInfo
from croniter import croniter
from pydantic import BaseModel, Field, field_validator, ConfigDict


class ScheduleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128, description="Unique human-readable schedule name")
    task_type: str = Field(..., min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_\-.:]+$")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Input arguments for child job executions")
    cron_expression: str = Field(..., min_length=5, max_length=64, description="Standard 5-part cron syntax (e.g. '*/5 * * * *')")
    timezone: str = Field(default="UTC", max_length=64, description="IANA timezone string (e.g. 'UTC', 'America/New_York')")
    enabled: bool = Field(default=True, description="Whether the schedule actively generates jobs")

    @field_validator("cron_expression")
    @classmethod
    def validate_cron(cls, v: str) -> str:
        v_clean = v.strip()
        if not croniter.is_valid(v_clean):
            raise ValueError(f"Invalid cron expression: '{v}'")
        return v_clean

    @field_validator("timezone")
    @classmethod
    def validate_tz(cls, v: str) -> str:
        v_clean = v.strip()
        try:
            ZoneInfo(v_clean)
        except Exception:
            raise ValueError(f"Unknown or invalid IANA timezone: '{v}'")
        return v_clean


class ScheduleUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    task_type: Optional[str] = Field(None, min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_\-.:]+$")
    payload: Optional[Dict[str, Any]] = None
    cron_expression: Optional[str] = Field(None, min_length=5, max_length=64)
    timezone: Optional[str] = Field(None, max_length=64)
    enabled: Optional[bool] = None

    @field_validator("cron_expression")
    @classmethod
    def validate_cron(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v_clean = v.strip()
            if not croniter.is_valid(v_clean):
                raise ValueError(f"Invalid cron expression: '{v}'")
            return v_clean
        return v

    @field_validator("timezone")
    @classmethod
    def validate_tz(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v_clean = v.strip()
            try:
                ZoneInfo(v_clean)
            except Exception:
                raise ValueError(f"Unknown or invalid IANA timezone: '{v}'")
            return v_clean
        return v


class ScheduleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    task_type: str
    payload_json: Dict[str, Any]
    cron_expression: str
    timezone: str
    enabled: bool
    next_run_at: datetime
    last_run_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class ScheduleListResponse(BaseModel):
    items: List[ScheduleResponse]
    total: int
