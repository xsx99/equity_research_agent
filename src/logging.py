"""Project logging helpers."""
import logging as py_logging
from logging.handlers import RotatingFileHandler
import os

_CONFIGURED = False


def _configure_logging(force: bool = False):
    global _CONFIGURED
    if _CONFIGURED and not force:
        return
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(py_logging, level_name, py_logging.INFO)
    log_format = "%(asctime)s %(levelname)s %(name)s %(message)s"

    handlers = [py_logging.StreamHandler()]

    log_file = os.getenv("LOG_FILE")
    log_dir = os.getenv("LOG_DIR")
    if log_file:
        file_path = os.path.expanduser(log_file)
    elif log_dir:
        file_path = os.path.join(os.path.expanduser(log_dir), "collector.log")
    else:
        file_path = None

    if file_path:
        dir_path = os.path.dirname(file_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
        try:
            max_bytes = int(os.getenv("LOG_MAX_BYTES", "10485760"))
        except ValueError:
            max_bytes = 10485760
        try:
            backup_count = int(os.getenv("LOG_BACKUP_COUNT", "5"))
        except ValueError:
            backup_count = 5
        handlers.append(
            RotatingFileHandler(
                file_path,
                maxBytes=max_bytes,
                backupCount=backup_count,
            )
        )

    py_logging.basicConfig(level=level, format=log_format, handlers=handlers, force=force)
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


def get_logger(name: str, force: bool = False) -> _StructuredLogger:
    _configure_logging(force=force)
    return _StructuredLogger(name)
