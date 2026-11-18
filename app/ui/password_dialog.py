"""Create/edit record dialog with inline strength meter and generator."""

from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLineEdit,
    QTextEdit,
    QWidget,
)

from app import config
from app.exceptions import PasswordManagerError, ValidationError
from app.models import PasswordRecord
from app.services.clipboard_service import ClipboardService
from app.services.generator import estimate_strength
from app.services.password_service import PasswordService
from app.ui.generator_dialog import open_generator
from app.ui.widgets import (
    BaseDialog,
    IconButton,
    MessageDialog,
    PasswordLineEdit,
    PrimaryButton,
    StrengthMeter,
    TextInputDialog,
    make_button,
    make_label,
)

logger = logging.getLogger(__name__)


class PasswordDialog(BaseDialog):
    def __init__(
        self,
        service: PasswordService,
        clipboard: ClipboardService,
        save_callback: Callable[[dict[str, object]], None],
        record: PasswordRecord | None = None,
        parent: QWidget | None = None,
    ) -> None:
        title = "Редактировать запись" if record else "Новая запись"
        super().__init__(parent, title, width=560, icon_name="edit" if record else "plus")
        self._service = service
        self._clipboard = clipboard
        self._save_callback = save_callback
        self._record = record
        self._build()
        if record is not None:
            self._populate(record)

    def _build(self) -> None:
        self.body.setSpacing(10)
        self.body.addWidget(make_label("Название сервиса *", "Caption"))
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("Например, GitHub")
        self.title_input.setMaxLength(config.MAX_TITLE_LENGTH)
        self.body.addWidget(self.title_input)

        self.body.addWidget(make_label("Логин", "Caption"))
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Имя пользователя или e-mail")
        self.username_input.setMaxLength(config.MAX_USERNAME_LENGTH)
        self.body.addWidget(self.username_input)

        self.body.addWidget(make_label("Пароль *", "Caption"))
        password_row = QHBoxLayout()
        password_row.setSpacing(8)
        self.password_input = PasswordLineEdit("Пароль")
        self.password_input.setMaxLength(config.MAX_PASSWORD_LENGTH)
        self.password_input.textChanged.connect(self._update_strength)
        password_row.addWidget(self.password_input, 1)
        generate_button = IconButton("key", "Сгенерировать пароль", 42, 18)
        generate_button.clicked.connect(self._open_generator)
        password_row.addWidget(generate_button)
        self.body.addLayout(password_row)

        self.strength = StrengthMeter()
        self.body.addWidget(self.strength)

        self.body.addWidget(make_label("Ссылка на сайт", "Caption"))
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("example.com или https://example.com")
        self.url_input.setMaxLength(config.MAX_URL_LENGTH)
        self.body.addWidget(self.url_input)

        self.body.addWidget(make_label("Категория", "Caption"))
        category_row = QHBoxLayout()
        category_row.setSpacing(8)
        self.category_combo = QComboBox()
        category_row.addWidget(self.category_combo, 1)
        add_category = IconButton("plus", "Создать категорию", 42, 17)
        add_category.clicked.connect(self._add_category)
        category_row.addWidget(add_category)
        self.body.addLayout(category_row)
        self._reload_categories()

        self.body.addWidget(make_label("Заметка", "Caption"))
        self.notes_input = QTextEdit()
        self.notes_input.setObjectName("NotesInput")
        self.notes_input.setPlaceholderText("Дополнительная информация (необязательно)")
        self.notes_input.setFixedHeight(72)
        self.notes_input.setAcceptRichText(False)
        self.body.addWidget(self.notes_input)

        self.favorite_checkbox = QCheckBox("Добавить в избранное")
        self.body.addWidget(self.favorite_checkbox)

        self.error = make_label("", "Error", wrap=True)
        self.error.hide()
        self.body.addWidget(self.error)

        self.footer.addStretch(1)
        cancel = make_button("Отмена", "Ghost")
        cancel.clicked.connect(self.reject)
        self.footer.addWidget(cancel)
        save = PrimaryButton("Сохранить", "check")
        save.clicked.connect(self._save)
        self.footer.addWidget(save)
        self.title_input.returnPressed.connect(self._save)
        self.username_input.returnPressed.connect(self._save)
        self.password_input.returnPressed.connect(self._save)
        self.url_input.returnPressed.connect(self._save)

    def _populate(self, record: PasswordRecord) -> None:
        self.title_input.setText(record.title)
        self.username_input.setText(record.username)
        self.password_input.setText(record.password)
        self.url_input.setText(record.url)
        self.notes_input.setPlainText(record.notes)
        self.favorite_checkbox.setChecked(record.favorite)
        index = self.category_combo.findData(record.category_id)
        self.category_combo.setCurrentIndex(index if index >= 0 else 0)
        self._update_strength(record.password)
        self.title_input.setFocus()
        self.title_input.selectAll()

    def _reload_categories(self, selected: str | None = None) -> None:
        current = selected or self.category_combo.currentData()
        self.category_combo.blockSignals(True)
        self.category_combo.clear()
        for category in self._service.settings.categories:
            self.category_combo.addItem(category.name, category.id)
        if current:
            index = self.category_combo.findData(current)
            if index >= 0:
                self.category_combo.setCurrentIndex(index)
        else:
            index = self.category_combo.findData("other")
            if index >= 0:
                self.category_combo.setCurrentIndex(index)
        self.category_combo.blockSignals(False)

    def _update_strength(self, text: str) -> None:
        if text:
            self.strength.set_result(estimate_strength(text))
        else:
            self.strength.clear()

    def _open_generator(self) -> None:
        password = open_generator(
            self,
            self._clipboard,
            self._service.settings.clipboard_clear_seconds,
            select_mode=True,
        )
        if password:
            self.password_input.setText(password)
            self.password_input.show_password(12)
            self._update_strength(password)

    def _add_category(self) -> None:
        name = TextInputDialog.get_text(
            self, "Новая категория", "Название категории", placeholder="Например, Облачные сервисы"
        )
        if not name:
            return
        try:
            category = self._service.add_category(name)
        except ValidationError as exc:
            MessageDialog.show_error(self, "Не удалось создать категорию", str(exc))
            return
        self._reload_categories(category.id)

    def _save(self) -> None:
        title = self.title_input.text().strip()
        password = self.password_input.text()
        if not title:
            self._show_error("Укажите название сервиса.")
            self.title_input.setFocus()
            return
        if not password:
            self._show_error("Укажите пароль или сгенерируйте его.")
            self.password_input.setFocus()
            return
        category_id = self.category_combo.currentData() or "other"
        payload: dict[str, object] = {
            "title": title,
            "username": self.username_input.text().strip(),
            "password": password,
            "url": self.url_input.text().strip(),
            "category_id": category_id,
            "notes": self.notes_input.toPlainText().strip(),
            "favorite": self.favorite_checkbox.isChecked(),
        }
        try:
            self._save_callback(payload)
        except PasswordManagerError as exc:
            self._show_error(str(exc))
            return
        except Exception:
            logger.exception("Failed to save record")
            self._show_error("Не удалось сохранить запись. Попробуйте ещё раз.")
            return
        self.accept()

    def _show_error(self, message: str) -> None:
        self.error.setText(message)
        self.error.show()
        self.adjustSize()

    def done(self, result: int) -> None:
        self.password_input.clear()
        self.username_input.clear()
        self.url_input.clear()
        self.notes_input.clear()
        self.title_input.clear()
        self.error.clear()
        super().done(result)
