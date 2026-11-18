"""Settings page and master-password change dialog."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app import config
from app.exceptions import (
    BackupError,
    InvalidMasterPasswordError,
    PasswordManagerError,
)
from app.services.backup_service import BackupService
from app.services.clipboard_service import ClipboardService
from app.services.generator import estimate_strength
from app.services.password_service import PasswordService
from app.security.key_manager import KeyManager
from app.ui.async_utils import TaskRunner
from app.ui.styles import SUCCESS, TEXT_MUTED
from app.ui.widgets import (
    BaseDialog,
    ConfirmDialog,
    MessageDialog,
    PasswordLineEdit,
    PrimaryButton,
    StrengthMeter,
    make_button,
    make_label,
)

logger = logging.getLogger(__name__)


class ChangePasswordDialog(BaseDialog):
    def __init__(self, key_manager: KeyManager, parent: QWidget | None = None) -> None:
        super().__init__(parent, "Смена мастер-пароля", width=520, icon_name="lock")
        self._keys = key_manager
        self._runner = TaskRunner(self)
        self._runner.succeeded.connect(self._on_success)
        self._runner.failed.connect(self._on_failure)
        self._build()

    def _build(self) -> None:
        self.body.addWidget(
            make_label(
                "Все записи будут перешифрованы новым ключом. "
                "Старый мастер-пароль перестанет работать.",
                "Muted",
                wrap=True,
            )
        )

        self.body.addWidget(make_label("Текущий мастер-пароль", "Caption"))
        self.current_input = PasswordLineEdit("Текущий пароль")
        self.current_input.setMaxLength(config.MAX_MASTER_PASSWORD_LENGTH)
        self.body.addWidget(self.current_input)

        self.body.addWidget(make_label("Новый мастер-пароль", "Caption"))
        self.new_input = PasswordLineEdit("Не менее 8 символов")
        self.new_input.setMaxLength(config.MAX_MASTER_PASSWORD_LENGTH)
        self.new_input.textChanged.connect(self._update_strength)
        self.body.addWidget(self.new_input)

        self.strength = StrengthMeter()
        self.body.addWidget(self.strength)

        self.body.addWidget(make_label("Повторите новый пароль", "Caption"))
        self.confirm_input = PasswordLineEdit("Повторите новый пароль")
        self.confirm_input.setMaxLength(config.MAX_MASTER_PASSWORD_LENGTH)
        self.confirm_input.returnPressed.connect(self._submit)
        self.body.addWidget(self.confirm_input)

        self.error = make_label("", "Error", wrap=True)
        self.error.hide()
        self.body.addWidget(self.error)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(3)
        self.progress.hide()
        self.body.addWidget(self.progress)

        self.footer.addStretch(1)
        cancel = make_button("Отмена", "Ghost")
        cancel.clicked.connect(self.reject)
        self.footer.addWidget(cancel)
        self.save_button = PrimaryButton("Изменить пароль", "lock")
        self.save_button.clicked.connect(self._submit)
        self.footer.addWidget(self.save_button)

    def _update_strength(self, text: str) -> None:
        if text:
            self.strength.set_result(estimate_strength(text))
        else:
            self.strength.clear()
        if self.error.isVisible():
            self.error.hide()
            self.adjustSize()

    def _submit(self) -> None:
        if self._runner.busy:
            return
        current = self.current_input.text()
        new = self.new_input.text()
        if not current:
            self._show_error("Введите текущий мастер-пароль.")
            return
        if len(new) < config.MIN_MASTER_PASSWORD_LENGTH:
            self._show_error(
                f"Новый пароль должен содержать не менее {config.MIN_MASTER_PASSWORD_LENGTH} символов."
            )
            return
        if new != self.confirm_input.text():
            self._show_error("Новые пароли не совпадают.")
            return
        self._set_busy(True)
        self._runner.run(lambda: self._keys.change_master_password(current, new))

    def _on_success(self, _result: object) -> None:
        self._set_busy(False)
        self.accept()

    def _on_failure(self, error: object) -> None:
        self._set_busy(False)
        if isinstance(error, InvalidMasterPasswordError):
            message = "Неверный текущий мастер-пароль."
        elif isinstance(error, PasswordManagerError):
            message = str(error)
        else:
            logger.error("Master password change failed: %s", type(error).__name__)
            message = "Не удалось изменить мастер-пароль. Данные не изменены."
        self._show_error(message)

    def _show_error(self, message: str) -> None:
        self.error.setText(message)
        self.error.show()
        self.adjustSize()

    def _set_busy(self, busy: bool) -> None:
        for field in (self.current_input, self.new_input, self.confirm_input):
            field.setEnabled(not busy)
        self.save_button.setEnabled(not busy)
        self.save_button.setText("Перешифровка…" if busy else "Изменить пароль")
        self.progress.setVisible(busy)
        self.adjustSize()

    def done(self, result: int) -> None:
        self.current_input.clear()
        self.new_input.clear()
        self.confirm_input.clear()
        self.error.clear()
        super().done(result)


class SettingsPage(QWidget):
    auto_lock_changed = Signal(int)
    lock_requested = Signal()
    restore_requested = Signal(str)
    password_changed = Signal()

    def __init__(
        self,
        service: PasswordService,
        backup_service: BackupService,
        key_manager: KeyManager,
        clipboard: ClipboardService,
        vault_path: Path,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._backups = backup_service
        self._keys = key_manager
        self._clipboard = clipboard
        self._vault_path = vault_path
        self._build()

    # ------------------------------------------------------------------ layout
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        container = QWidget()
        content = QVBoxLayout(container)
        content.setContentsMargins(34, 26, 34, 34)
        content.setSpacing(18)

        content.addWidget(make_label("Настройки", "Heading"))
        content.addWidget(
            make_label(
                "Параметры безопасности, резервное копирование и сведения о приложении.",
                "Muted",
                wrap=True,
            )
        )

        content.addWidget(self._build_security_section())
        content.addWidget(self._build_backup_section())
        content.addWidget(self._build_about_section())
        content.addStretch(1)

        scroll.setWidget(container)
        outer.addWidget(scroll)

    def _section(self, title: str, subtitle: str = "") -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName("SectionCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)
        layout.addWidget(make_label(title, "SectionTitle"))
        if subtitle:
            layout.addWidget(make_label(subtitle, "Muted", wrap=True))
        return card, layout

    def _row(self, title: str, description: str, control: QWidget) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)
        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(3)
        text_layout.addWidget(make_label(title))
        text_layout.addWidget(make_label(description, "MutedSmall", wrap=True))
        layout.addLayout(text_layout, 1)
        layout.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
        return row

    def _divider(self) -> QFrame:
        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet("background: #222834;")
        return divider

    def _build_security_section(self) -> QFrame:
        card, layout = self._section(
            "Безопасность",
            "Хранилище автоматически блокируется после периода бездействия. "
            "Ключ шифрования при этом удаляется из памяти.",
        )

        self.auto_lock_combo = QComboBox()
        for minutes, label in config.AUTO_LOCK_OPTIONS:
            self.auto_lock_combo.addItem(label, minutes)
        self._select_combo(self.auto_lock_combo, self._service.settings.auto_lock_minutes)
        self.auto_lock_combo.setFixedWidth(190)
        self.auto_lock_combo.currentIndexChanged.connect(self._on_auto_lock_changed)
        layout.addWidget(
            self._row(
                "Автоматическая блокировка",
                "Блокировать хранилище при отсутствии активности",
                self.auto_lock_combo,
            )
        )
        layout.addWidget(self._divider())

        self.clipboard_combo = QComboBox()
        for seconds, label in config.CLIPBOARD_OPTIONS:
            self.clipboard_combo.addItem(label, seconds)
        self._select_combo(self.clipboard_combo, self._service.settings.clipboard_clear_seconds)
        self.clipboard_combo.setFixedWidth(190)
        self.clipboard_combo.currentIndexChanged.connect(self._on_clipboard_changed)
        layout.addWidget(
            self._row(
                "Очистка буфера обмена",
                "Удалять скопированный пароль, если буфер не изменён",
                self.clipboard_combo,
            )
        )
        layout.addWidget(self._divider())

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        change_button = make_button("Сменить мастер-пароль", "Ghost", "lock", TEXT_MUTED)
        change_button.clicked.connect(self._change_password)
        buttons.addWidget(change_button)
        lock_button = make_button("Заблокировать сейчас", "Ghost", "unlock", TEXT_MUTED)
        lock_button.clicked.connect(self.lock_requested.emit)
        buttons.addWidget(lock_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        return card

    def _build_backup_section(self) -> QFrame:
        card, layout = self._section(
            "Резервные копии",
            "Копия — это снимок зашифрованного хранилища. Пароль не требуется для её создания, "
            "а файл остаётся зашифрованным.",
        )

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        create = PrimaryButton("Создать копию", "download")
        create.clicked.connect(self._create_backup)
        buttons.addWidget(create)
        verify = make_button("Проверить копию", "Ghost", "check", SUCCESS)
        verify.clicked.connect(self._verify_backup)
        buttons.addWidget(verify)
        restore = make_button("Восстановить", "Ghost", "upload", TEXT_MUTED)
        restore.clicked.connect(self._restore_backup)
        buttons.addWidget(restore)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        hint = make_label(
            "Восстановление заменит текущее хранилище. Перед заменой автоматически создаётся "
            "страховочная копия. После восстановления потребуется ввести мастер-пароль из копии.",
            "MutedSmall",
            wrap=True,
        )
        layout.addWidget(hint)
        return card

    def _build_about_section(self) -> QFrame:
        card, layout = self._section("О приложении")
        layout.addWidget(self._info_row("Приложение", f"{config.APP_NAME} {config.APP_VERSION}"))
        layout.addWidget(self._info_row("Формат хранилища", f"v{config.VAULT_FORMAT_VERSION}"))
        layout.addWidget(
            self._info_row(
                "Шифрование",
                "AES-256-GCM · Argon2id · уникальный nonce для каждой записи",
            )
        )

        path_label = QLabel(str(self._vault_path))
        path_label.setObjectName("MutedSmall")
        path_label.setWordWrap(True)
        path_label.setTextFormat(Qt.TextFormat.PlainText)
        path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(make_label("Расположение данных", "Caption"))
        layout.addWidget(path_label)

        buttons = QHBoxLayout()
        open_folder = make_button("Открыть папку", "Ghost", "folder", TEXT_MUTED)
        open_folder.clicked.connect(self._open_data_folder)
        buttons.addWidget(open_folder)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        layout.addWidget(
            make_label(
                "Приложение не использует сеть, облако или удалённые серверы. "
                "Все данные остаются на этом компьютере.",
                "MutedSmall",
                wrap=True,
            )
        )
        return card

    def _info_row(self, title: str, value: str) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(make_label(title, "Muted"))
        layout.addStretch(1)
        value_label = make_label(value)
        value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(value_label)
        return row

    @staticmethod
    def _select_combo(combo: QComboBox, value: int) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    # ------------------------------------------------------------------ actions
    def _on_auto_lock_changed(self) -> None:
        value = int(self.auto_lock_combo.currentData())
        candidate = self._service.settings
        old = candidate.auto_lock_minutes
        candidate.auto_lock_minutes = value
        try:
            self._service.save_settings(candidate)
        except PasswordManagerError as exc:
            candidate.auto_lock_minutes = old
            self._select_combo(self.auto_lock_combo, old)
            MessageDialog.show_error(self, "Не удалось сохранить настройку", str(exc))
            return
        self.auto_lock_changed.emit(value)

    def _on_clipboard_changed(self) -> None:
        value = int(self.clipboard_combo.currentData())
        candidate = self._service.settings
        old = candidate.clipboard_clear_seconds
        candidate.clipboard_clear_seconds = value
        try:
            self._service.save_settings(candidate)
        except PasswordManagerError as exc:
            candidate.clipboard_clear_seconds = old
            self._select_combo(self.clipboard_combo, old)
            MessageDialog.show_error(self, "Не удалось сохранить настройку", str(exc))
            return
        self._clipboard.set_clear_after(value)

    def _change_password(self) -> None:
        dialog = ChangePasswordDialog(self._keys, self)
        if dialog.exec() == ChangePasswordDialog.DialogCode.Accepted:
            MessageDialog.show_success(
                self,
                "Мастер-пароль изменён",
                "Все записи перешифрованы новым ключом. "
                "Используйте новый мастер-пароль при следующей разблокировке.",
            )
            self.password_changed.emit()

    def _create_backup(self) -> None:
        suggested = str(Path.home() / BackupService.suggested_filename())
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить резервную копию",
            suggested,
            "Зашифрованная резервная копия (*.pmvault);;Все файлы (*)",
        )
        if not filename:
            return
        try:
            path = self._backups.create_backup(filename)
        except (PasswordManagerError, OSError) as exc:
            MessageDialog.show_error(self, "Не удалось создать копию", str(exc))
            return
        MessageDialog.show_success(
            self,
            "Резервная копия создана",
            f"Файл сохранён:\n{path}\n\nКопия зашифрована и содержит все записи и настройки.",
        )

    def _verify_backup(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Проверить резервную копию",
            str(Path.home()),
            "Зашифрованная резервная копия (*.pmvault);;Все файлы (*)",
        )
        if not filename:
            return
        try:
            info = self._backups.validate_backup(filename)
        except (PasswordManagerError, OSError) as exc:
            MessageDialog.show_error(self, "Ошибка проверки", str(exc))
            return
        if not info.valid:
            MessageDialog.show_error(
                self,
                "Копия повреждена",
                f"Файл не прошёл проверку целостности.\n\n{info.message}",
            )
            return
        try:
            crypto_note = self._cryptographic_note(filename, info)
        except BackupError as exc:
            MessageDialog.show_error(
                self,
                "Копия повреждена",
                f"Шифротекст не прошёл проверку.\n\n{exc}",
            )
            return
        created = info.created_at.replace("T", " ")[:16] if info.created_at else "неизвестно"
        MessageDialog.show_success(
            self,
            "Копия корректна",
            "Файл цел и содержит зашифрованное хранилище.\n\n"
            f"Записей: {info.record_count}\n"
            f"Формат: v{info.format_version}\n"
            f"Создано: {created}\n"
            f"Версия приложения: {info.app_version or 'неизвестна'}\n\n"
            f"{crypto_note}",
        )

    def _restore_backup(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Восстановить из резервной копии",
            str(Path.home()),
            "Зашифрованная резервная копия (*.pmvault);;Все файлы (*)",
        )
        if not filename:
            return
        try:
            info = self._backups.validate_backup(filename)
        except (PasswordManagerError, OSError) as exc:
            MessageDialog.show_error(self, "Ошибка проверки", str(exc))
            return
        if not info.valid:
            MessageDialog.show_error(
                self,
                "Копия повреждена",
                f"Восстановление невозможно.\n\n{info.message}",
            )
            return
        try:
            crypto_note = self._cryptographic_note(filename, info)
        except BackupError as exc:
            MessageDialog.show_error(
                self,
                "Копия повреждена",
                f"Восстановление невозможно: шифротекст не прошёл проверку.\n\n{exc}",
            )
            return
        if not ConfirmDialog.ask(
            self,
            "Заменить текущее хранилище?",
            f"Будет восстановлена копия с {info.record_count} записями.\n"
            f"{crypto_note}\n\n"
            "Текущее хранилище будет заменено, но перед этим автоматически сохранится "
            "страховочная копия. После восстановления потребуется ввести мастер-пароль "
            "от резервной копии.",
            "Восстановить",
            danger=True,
        ):
            return
        self.restore_requested.emit(filename)

    def _cryptographic_note(self, filename: str, info) -> str:
        if info.vault_id != self._keys.vault_id:
            return (
                "Криптографическая проверка недоступна: копия создана в другом хранилище. "
                "Целостность шифротекста будет проверена после ввода её мастер-пароля."
            )
        if info.key_version != self._keys.key_version:
            return (
                "Структурная проверка пройдена. Копия создана до смены мастер-пароля, "
                "поэтому полная проверка текущим ключом недоступна."
            )
        verified = self._backups.verify_cryptographic(filename, self._keys)
        return f"Криптографическая проверка пройдена: {verified} записей."

    def _open_data_folder(self) -> None:
        folder = self._vault_path.parent
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
