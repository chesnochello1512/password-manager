"""Master-password creation and unlock screen."""

from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QCursor
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from app import config
from app.exceptions import (
    InvalidMasterPasswordError,
    PasswordManagerError,
    VaultCorruptedError,
    VaultError,
)
from app.services.generator import estimate_strength
from app.ui import icons
from app.ui.async_utils import TaskRunner
from app.ui.styles import ACCENT, TEXT_MUTED, TEXT_SECONDARY
from app.ui.widgets import (
    DragHeader,
    IconButton,
    PasswordLineEdit,
    PrimaryButton,
    StrengthMeter,
    make_label,
)

logger = logging.getLogger(__name__)


class LoginWindow(QWidget):
    authenticated = Signal()
    closed = Signal()

    def __init__(
        self,
        setup_mode: bool,
        create_callback: Callable[[str], None],
        unlock_callback: Callable[[str], None],
        notice: str = "",
    ) -> None:
        super().__init__(None)
        self._setup_mode = setup_mode
        self._create_callback = create_callback
        self._unlock_callback = unlock_callback
        self._notice = notice
        self._runner = TaskRunner(self)
        self._allow_close_signal = True

        self.setWindowTitle(config.APP_NAME)
        self.setWindowIcon(icons.icon("logo", ACCENT, 32))
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(500)

        self._build()
        self._runner.succeeded.connect(self._on_success)
        self._runner.failed.connect(self._on_failure)

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(22, 22, 22, 22)
        surface = QFrame()
        surface.setObjectName("LoginSurface")
        shadow = QGraphicsDropShadowEffect(surface)
        shadow.setBlurRadius(60)
        shadow.setOffset(0, 14)
        shadow.setColor(QColor(0, 0, 0, 170))
        surface.setGraphicsEffect(shadow)
        outer.addWidget(surface)

        content = QVBoxLayout(surface)
        content.setContentsMargins(36, 26, 36, 26)
        content.setSpacing(0)

        header = DragHeader()
        header.setFixedHeight(28)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(9)
        logo = QLabel()
        logo.setPixmap(icons.pixmap("logo", ACCENT, 22))
        header_layout.addWidget(logo)
        header_layout.addWidget(make_label("Password Manager", "AppName"))
        header_layout.addStretch(1)
        close_button = IconButton("x", "Закрыть", 28, 15)
        close_button.clicked.connect(self._close)
        header_layout.addWidget(close_button)
        content.addWidget(header)

        content.addSpacing(24)
        heading = "Создайте мастер-пароль" if self._setup_mode else "Разблокируйте хранилище"
        content.addWidget(make_label(heading, "Heading"))
        content.addSpacing(8)

        description = (
            "Мастер-пароль защищает все сохранённые данные. "
            "Его нельзя восстановить — сохраните его в надёжном месте."
            if self._setup_mode
            else "Введите мастер-пароль, чтобы получить доступ к вашим записям."
        )
        description_label = make_label(description, "Muted", wrap=True)
        description_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px;")
        content.addWidget(description_label)

        if self._notice:
            content.addSpacing(10)
            notice = make_label(self._notice, "Success", wrap=True)
            notice.setStyleSheet("color: #3ED598; font-size: 12px;")
            content.addWidget(notice)

        content.addSpacing(20)
        content.addWidget(make_label("Мастер-пароль", "Caption"))
        content.addSpacing(6)
        self.password = PasswordLineEdit("Введите мастер-пароль")
        self.password.setMaxLength(config.MAX_MASTER_PASSWORD_LENGTH)
        self.password.returnPressed.connect(self._submit)
        self.password.textChanged.connect(self._on_password_changed)
        content.addWidget(self.password)

        self.strength = StrengthMeter()
        self.strength.hide()
        content.addSpacing(8)
        content.addWidget(self.strength)

        self.confirm = PasswordLineEdit("Повторите мастер-пароль")
        self.confirm.setMaxLength(config.MAX_MASTER_PASSWORD_LENGTH)
        self.confirm.setVisible(self._setup_mode)
        self.confirm.returnPressed.connect(self._submit)
        if self._setup_mode:
            content.addSpacing(12)
            content.addWidget(make_label("Подтверждение пароля", "Caption"))
            content.addSpacing(6)
            content.addWidget(self.confirm)

        self.error = make_label("", "Error", wrap=True)
        self.error.hide()
        content.addSpacing(8)
        content.addWidget(self.error)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(3)
        self.progress.hide()
        content.addSpacing(8)
        content.addWidget(self.progress)

        content.addSpacing(14)
        self.submit_button = PrimaryButton(
            "Создать хранилище" if self._setup_mode else "Разблокировать",
            "lock" if self._setup_mode else "unlock",
        )
        self.submit_button.setMinimumHeight(44)
        self.submit_button.clicked.connect(self._submit)
        content.addWidget(self.submit_button)

        if self._setup_mode:
            content.addSpacing(10)
            hint = make_label(
                f"Минимум {config.MIN_MASTER_PASSWORD_LENGTH} символов. "
                "Ключ создаётся через Argon2id и никогда не сохраняется.",
                "MutedSmall",
                wrap=True,
            )
            content.addWidget(hint)

        content.addSpacing(22)
        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet("background: #222834;")
        content.addWidget(divider)
        content.addSpacing(14)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        shield = QLabel()
        shield.setPixmap(icons.pixmap("shield", TEXT_MUTED, 15))
        footer.addWidget(shield)
        footer.addWidget(
            make_label("AES-256-GCM · Argon2id · данные не покидают устройство", "MutedSmall")
        )
        footer.addStretch(1)
        content.addLayout(footer)

        self.password.setFocus()

    # ------------------------------------------------------------------ actions
    def _close(self) -> None:
        self.closed.emit()

    def close_silently(self) -> None:
        self._allow_close_signal = False
        self.close()

    def shutdown(self) -> None:
        """Wait for a pending create/unlock worker before the app tears down."""

        self._runner.shutdown()

    def _on_password_changed(self, text: str) -> None:
        if self._setup_mode:
            self.strength.setVisible(bool(text))
            if text:
                self.strength.set_result(estimate_strength(text))
            else:
                self.strength.clear()
        if self.error.isVisible():
            self._set_error("")

    def _submit(self) -> None:
        if self._runner.busy:
            return
        password = self.password.text()
        if not password:
            self._set_error("Введите мастер-пароль.")
            self.password.setFocus()
            return

        if self._setup_mode:
            if len(password) < config.MIN_MASTER_PASSWORD_LENGTH:
                self._set_error(
                    f"Мастер-пароль должен содержать не менее {config.MIN_MASTER_PASSWORD_LENGTH} символов."
                )
                self.password.setFocus()
                return
            if password != self.confirm.text():
                self._set_error("Пароли не совпадают.")
                self.confirm.setFocus()
                self.confirm.selectAll()
                return
            task = lambda: self._create_callback(password)  # noqa: E731
        else:
            task = lambda: self._unlock_callback(password)  # noqa: E731

        self._set_busy(True)
        self._runner.run(task)

    def _on_success(self, _result: object) -> None:
        self._set_busy(False)
        self.authenticated.emit()

    def _on_failure(self, error: object) -> None:
        self._set_busy(False)
        if isinstance(error, InvalidMasterPasswordError):
            message = "Неверный мастер-пароль. Попробуйте ещё раз."
        elif isinstance(error, VaultCorruptedError | VaultError | PasswordManagerError):
            message = str(error)
        else:
            logger.error("Unlock failed: %s", type(error).__name__)
            message = "Не удалось открыть хранилище. Проверьте файл данных."
        self._set_error(message)
        self.password.selectAll()
        self.password.setFocus()

    def _set_error(self, message: str) -> None:
        if not message:
            self.error.hide()
            self.adjustSize()
            return
        self.error.setText(message)
        self.error.show()
        self.adjustSize()

    def _set_busy(self, busy: bool) -> None:
        self.password.setEnabled(not busy)
        self.confirm.setEnabled(not busy)
        self.submit_button.setEnabled(not busy)
        self.progress.setVisible(busy)
        if busy:
            self.submit_button.setText("Проверяем…" if not self._setup_mode else "Создаём…")
            self.setCursor(QCursor(Qt.CursorShape.WaitCursor))
        else:
            self.submit_button.setText(
                "Создать хранилище" if self._setup_mode else "Разблокировать"
            )
            self.unsetCursor()
        self.adjustSize()

    # ------------------------------------------------------------------ window
    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.adjustSize()
        screen = self.screen()
        if screen is not None:
            geometry = screen.availableGeometry()
            self.move(
                geometry.center().x() - self.width() // 2,
                geometry.center().y() - self.height() // 2,
            )
        self.password.setFocus()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self._close()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        self.password.clear()
        self.confirm.clear()
        self.error.clear()
        self.strength.clear()
        if self._allow_close_signal:
            self.closed.emit()
        event.accept()
        super().closeEvent(event)
