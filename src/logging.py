"""Project logging helpers."""
import logging as py_logging
import os

_CONFIGURED = False


def _configure_logging():
    global _CONFIGURED
    if _CONFIGURED:
        return
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(py_logging, level_name, py_logging.INFO)
    py_logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    _CONFIGURED = True


class _StructuredLogger:
    """Logger wrapper that accepts key/value pairs as kwargs."""

    def __init__(self, name: str):
        self._logger = py_logging.getLogger(name)

    def _log(self, level: int, msg: str, **kwargs):
        exc_info = kwargs.pop("exc_info", None)
        stack_info = kwargs.pop("stack_info", None)
        if kwargs:
            kv = " ".join(f"{k}={v}" for k, v in kwargs.items())
            msg = f"{msg} {kv}"
        self._logger.log(level, msg, exc_info=exc_info, stack_info=stack_info)

    def debug(self, msg: str, **kwargs):
        self._log(py_logging.DEBUG, msg, **kwargs)

    def info(self, msg: str, **kwargs):
        self._log(py_logging.INFO, msg, **kwargs)

    def warning(self, msg: str, **kwargs):
        self._log(py_logging.WARNING, msg, **kwargs)

    def error(self, msg: str, **kwargs):
        self._log(py_logging.ERROR, msg, **kwargs)


def get_logger(name: str) -> _StructuredLogger:
    _configure_logging()
    return _StructuredLogger(name)
