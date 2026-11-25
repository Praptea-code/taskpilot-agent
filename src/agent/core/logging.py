import json
import logging
from contextvars import ContextVar
from datetime import datetime, timezone

LOG_CONTEXT: ContextVar[dict[str, object]] = ContextVar("log_context", default={})


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        payload.update(LOG_CONTEXT.get())
        for key in ("user_id", "goal_id", "action_id", "path"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, sort_keys=True)


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)


def bind_log_context(**values: object) -> object:
    merged = {**LOG_CONTEXT.get(), **values}
    return LOG_CONTEXT.set(merged)


def reset_log_context(token: object) -> None:
    LOG_CONTEXT.reset(token)
