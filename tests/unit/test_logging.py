import json
import logging
from app.core.logging import JSONFormatter, configure_logging


def test_json_formatter_standard_fields():
    """Verifies that JSONFormatter produces valid JSON with required standard metadata."""
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=42,
        msg="Processing job %s",
        args=("job-abc-123",),
        exc_info=None,
    )

    output = formatter.format(record)
    data = json.loads(output)

    assert data["level"] == "INFO"
    assert data["logger"] == "test.logger"
    assert data["message"] == "Processing job job-abc-123"
    assert "timestamp" in data
    assert data["line"] == 42


def test_json_formatter_extra_context():
    """Verifies that extra contextual fields are extracted into the context object."""
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="worker.engine",
        level=logging.WARNING,
        pathname=__file__,
        lineno=100,
        msg="Task retrying due to transient failure",
        args=(),
        exc_info=None,
    )
    record.__dict__["job_id"] = "00000000-0000-0000-0000-000000000001"
    record.__dict__["worker_id"] = "worker-primary-1"
    record.__dict__["attempt_number"] = 2

    output = formatter.format(record)
    data = json.loads(output)

    assert "context" in data
    assert data["context"]["job_id"] == "00000000-0000-0000-0000-000000000001"
    assert data["context"]["worker_id"] == "worker-primary-1"
    assert data["context"]["attempt_number"] == 2


def test_json_formatter_exception_traceback():
    """Verifies that exception information is captured as a traceback string."""
    formatter = JSONFormatter()
    try:
        raise ValueError("Critical simulated failure")
    except ValueError:
        import sys
        exc_info = sys.exc_info()

    record = logging.LogRecord(
        name="test.error",
        level=logging.ERROR,
        pathname=__file__,
        lineno=80,
        msg="Unhandled task exception",
        args=(),
        exc_info=exc_info,
    )

    output = formatter.format(record)
    data = json.loads(output)

    assert data["level"] == "ERROR"
    assert "exception" in data
    assert "ValueError: Critical simulated failure" in data["exception"]


def test_configure_logging_integration():
    """Verifies that configure_logging applies handlers without error."""
    configure_logging(level="DEBUG", json_format=True)
    root = logging.getLogger()
    assert len(root.handlers) >= 1
    assert isinstance(root.handlers[0].formatter, JSONFormatter)
