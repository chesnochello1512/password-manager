"""Password Manager entry point."""

from __future__ import annotations

import ctypes
import logging
import sys
from pathlib import Path

from PySide6.QtCore import QLockFile, Qt
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from app import config
from app.controller import ApplicationController
from app.logging_setup import install_exception_hook, setup_logging
from app.ui import icons
from app.ui.styles import ACCENT, apply_theme


def _resource_path(relative: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / relative


def _configure_windows_app_id() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(  # type: ignore[attr-defined]
            f"{config.APP_SLUG}.{config.APP_VERSION}"
        )
    except (AttributeError, OSError):
        pass


def main() -> int:
    _configure_windows_app_id()
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName(config.APP_NAME)
    app.setApplicationDisplayName(config.APP_NAME)
    app.setApplicationVersion(config.APP_VERSION)
    app.setOrganizationName("Local")
    app.setDesktopFileName("password-manager")

    apply_theme(app)
    icon_path = _resource_path("assets/icon.png")
    if icon_path.is_file():
        app.setWindowIcon(QIcon(str(icon_path)))
    else:
        app.setWindowIcon(icons.icon("logo", ACCENT, 64))
    try:
        config.ensure_directories()
        setup_logging()
    except OSError as exc:
        QMessageBox.critical(
            None,
            config.APP_NAME,
            "Не удалось создать каталог данных приложения.\n\n"
            f"{exc}\n\nПроверьте права доступа к профилю пользователя.",
        )
        return 1
    logging.getLogger(__name__).info("Starting %s %s", config.APP_NAME, config.APP_VERSION)

    lock = QLockFile(str(config.data_dir() / "app.lock"))
    lock.setStaleLockTime(30_000)
    if not lock.tryLock(200):
        QMessageBox.critical(
            None,
            config.APP_NAME,
            "Password Manager уже запущен.\nЗакройте другое окно приложения и попробуйте снова.",
        )
        return 1

    install_exception_hook()
    controller = ApplicationController(app)
    controller.start()
    exit_code = app.exec()
    try:
        lock.unlock()
    except Exception:
        pass
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
