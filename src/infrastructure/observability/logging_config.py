"""
Structured logging configuration using structlog.

Produces JSON-formatted log lines enriched with timestamps, log levels,
service metadata, and optional request context. Designed for consumption
by centralised log aggregation systems (ELK, Loki, etc.).
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

# ======================================================================
# Constants
# ======================================================================

SERVICE_NAME: str = "eu-mt-platform"


# ======================================================================
# Custom processors
# ======================================================================


def add_service_name(logger: Any, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Inject the service name into every log event."""
    event_dict.setdefault("service", SERVICE_NAME)
    return event_dict


# ======================================================================
# Setup
# ======================================================================


def setup_logging(log_level: str = "INFO") -> None:
    """
    Configure structlog and the stdlib logging bridge for JSON output.

    Call this once at application startup (e.g. in a FastAPI ``lifespan``
    or in ``main``).

    Parameters
    ----------
    log_level:
        Minimum severity level as a string (``DEBUG``, ``INFO``, ``WARNING``,
        ``ERROR``, ``CRITICAL``).
    """

    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # Shared processor chain used by both structlog and the stdlib bridge.
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        add_service_name,  # type: ignore[list-item]
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    # Configure structlog itself.
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Build a stdlib formatter that renders structlog events as JSON.
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
    )

    # Wire up the root logger.
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(numeric_level)


# ======================================================================
# Logger factory
# ======================================================================


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    Return a bound structlog logger pre-populated with the given *name*.

    Additional context can be attached via ``.bind()``::

        log = get_logger("billing")
        log = log.bind(tenant_id="t-123")
        log.info("Invoice generated", amount=42.50)
    """
    return structlog.get_logger(name)  # type: ignore[no-any-return]
