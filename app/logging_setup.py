"""File logging with no sensitive payloads."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app import config


def setup_logging() -> Path:
    config.ensure_directories()
    log_path = config.logs_dir() / "app.log"
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    for handler in list(root.handlers):
        if isinstance(handler, RotatingFileHandler | logging.StreamHandler):
            root.removeHandler(handler)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    try:
        file_handler = RotatingFileHandler(
            log_path, maxBytes=1_500_000, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError:
        pass

    stream_handler = logging.StreamHandler(sys.stderr) if sys.stderr is not None else None
    if stream_handler is not None:
        stream_handler.setFormatter(formatter)
        root.addHandler(stream_handler)
    return log_path


def install_exception_hook() -> None:
    from PySide6.QtWidgets import QApplication, QMessageBox

    def handle(exc_type, exc_value, traceback) -> None:
        logging.getLogger(__name__).critical(
            "Unhandled exception", exc_info=(exc_type, exc_value, traceback)
        )
        if QApplication.instance() is not None:
            QMessageBox.critical(
                None,
                "Непредвиденная ошибка",
                "Приложение столкнулось с непредвиденной ошибкой.\n"
                "Подробности записаны в журнал приложения.",
            )

    sys.excepthook = handle
