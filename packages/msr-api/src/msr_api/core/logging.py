"""structlog for our logs and, through the stdlib formatter, for every library's.

`LOG_FORMAT=JSON` renders one JSON object per line; `STANDARD` renders readable key=value lines.
Context bound with `structlog.contextvars` (the correlation id) appears on every line, including
library lines logged while it's bound.
"""

import logging

import structlog

# Chatty dependency loggers default to WARNING; LOG_LEVELS overrides any logger.
NOISY = (
    "amqp",
    "celery",
    "httpcore",
    "httpx",
    "kombu",
    "psycopg.pool",
    "sse_starlette",
    "uvicorn.access",
    "watchfiles",
)


def parse_levels(spec: str) -> dict[str, str]:
    """`kombu=INFO, psycopg=DEBUG` → {"kombu": "INFO", "psycopg": "DEBUG"}."""
    levels = {}
    for item in filter(None, (part.strip() for part in spec.split(","))):
        name, sep, level = item.partition("=")
        if not sep or not name.strip() or not level.strip():
            raise ValueError(f"LOG_LEVELS entries look like name=LEVEL, got {item!r}")
        levels[name.strip()] = level.strip().upper()
    return levels


def configure_logging(level: str, fmt: str, overrides: str = "") -> None:
    shared: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]
    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer()
        if fmt == "JSON"
        else structlog.dev.ConsoleRenderer(colors=False)
    )
    structlog.configure(
        processors=[
            *shared,
            structlog.processors.format_exc_info,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    handler = logging.StreamHandler()
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared,
            processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, renderer],
        )
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    # Uvicorn installs its own handlers; route its loggers through ours instead.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True
    for name in NOISY:
        logging.getLogger(name).setLevel(logging.WARNING)
    for name, name_level in parse_levels(overrides).items():
        logging.getLogger(name).setLevel(name_level)
