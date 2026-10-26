import pytest
from pydantic import ValidationError
from app.schemas.schedule import ScheduleCreate, ScheduleUpdate


def test_valid_schedule_create():
    """Verifies that a valid schedule create payload passes validation."""
    data = ScheduleCreate(
        name="daily-cleanup",
        task_type="compute_hash",
        payload={"target": "temp_files"},
        cron_expression="0 2 * * *",
        timezone="America/New_York",
        enabled=True,
    )
    assert data.name == "daily-cleanup"
    assert data.cron_expression == "0 2 * * *"
    assert data.timezone == "America/New_York"
    assert data.enabled is True


def test_invalid_cron_syntax_rejected():
    """Verifies that malformed or invalid cron syntax is rejected with ValidationError."""
    with pytest.raises(ValidationError) as exc:
        ScheduleCreate(
            name="broken-cron",
            task_type="compute_hash",
            cron_expression="not-a-cron-expression",
        )
    assert "Invalid cron expression" in str(exc.value)


def test_invalid_timezone_rejected():
    """Verifies that unrecognized IANA timezones are rejected with ValidationError."""
    with pytest.raises(ValidationError) as exc:
        ScheduleCreate(
            name="broken-tz",
            task_type="compute_hash",
            cron_expression="*/15 * * * *",
            timezone="Mars/Phobos",
        )
    assert "Unknown or invalid IANA timezone" in str(exc.value)


def test_schedule_update_partial_validation():
    """Verifies that partial updates validate changed fields and allow None for unset."""
    update = ScheduleUpdate(cron_expression="0 0 1 * *", enabled=False)
    assert update.cron_expression == "0 0 1 * *"
    assert update.enabled is False
    assert update.name is None

    with pytest.raises(ValidationError) as exc:
        ScheduleUpdate(timezone="Invalid/Timezone")
    assert "Unknown or invalid IANA timezone" in str(exc.value)
