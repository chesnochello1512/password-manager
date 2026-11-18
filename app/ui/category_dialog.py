"""Category management dialog."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.exceptions import PasswordManagerError
from app.services.password_service import PasswordService
from app.ui import icons
from app.ui.styles import ACCENT
from app.ui.widgets import (
    BaseDialog,
    ConfirmDialog,
    IconButton,
    MessageDialog,
    PrimaryButton,
    TextInputDialog,
    make_label,
)


def _records_word(count: int) -> str:
    if count % 10 == 1 and count % 100 != 11:
        return "запись"
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return "записи"
    return "записей"


class CategoryDialog(BaseDialog):
    changed = Signal()
    def __init__(self, service: PasswordService, parent: QWidget | None = None) -> None:
        super().__init__(parent, "Категории", width=520, icon_name="sliders")
        self._service = service
        self._build()
        self._refresh()

    def _build(self) -> None:
        self.body.addWidget(
            make_label(
                "Категории можно переименовывать, добавлять и удалять. "
                "При удалении записи переносятся в «Другое».",
                "Muted",
                wrap=True,
            )
        )

        add_row = QHBoxLayout()
        add_row.setSpacing(8)
        self.new_name = QLineEdit()
        self.new_name.setPlaceholderText("Название новой категории")
        self.new_name.returnPressed.connect(self._add)
        add_row.addWidget(self.new_name, 1)
        add_button = PrimaryButton("Добавить", "plus")
        add_button.clicked.connect(self._add)
        add_row.addWidget(add_button)
        self.body.addLayout(add_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setMinimumHeight(220)
        scroll.setMaximumHeight(340)
        self.rows_widget = QWidget()
        self.rows_layout = QVBoxLayout(self.rows_widget)
        self.rows_layout.setContentsMargins(0, 2, 0, 2)
        self.rows_layout.setSpacing(6)
        self.rows_layout.addStretch(1)
        scroll.setWidget(self.rows_widget)
        self.body.addWidget(scroll)

        self.error = make_label("", "Error", wrap=True)
        self.error.hide()
        self.body.addWidget(self.error)

        self.footer.addStretch(1)
        close = PrimaryButton("Готово", "check")
        close.clicked.connect(self.accept)
        self.footer.addWidget(close)

    def _refresh(self) -> None:
        while self.rows_layout.count() > 1:
            item = self.rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        categories = sorted(self._service.settings.categories, key=lambda item: (item.order, item.name.casefold()))
        for index, category in enumerate(categories):
            row = self._make_row(category.id, category.name, category.id == "other")
            self.rows_layout.insertWidget(index, row)

    def _make_row(self, category_id: str, name: str, is_other: bool) -> QFrame:
        row = QFrame()
        row.setObjectName("CategoryRow")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(12, 6, 8, 6)
        layout.setSpacing(8)
        icon_label = make_label()
        icon_label.setPixmap(icons.pixmap(icons.category_icon_id(category_id), ACCENT, 16))
        layout.addWidget(icon_label)
        layout.addWidget(make_label(name), 1)
        count = self._service.count_by_category(category_id)
        layout.addWidget(make_label(f"{count} {_records_word(count)}", "MutedSmall"))

        rename = IconButton("edit", "Переименовать", 30, 15)
        rename.clicked.connect(lambda: self._rename(category_id, name))
        layout.addWidget(rename)

        delete = IconButton("trash", "Удалить категорию", 30, 15)
        delete.setEnabled(not is_other)
        delete.clicked.connect(lambda: self._delete(category_id, name))
        layout.addWidget(delete)
        return row

    def _add(self) -> None:
        name = " ".join(self.new_name.text().split())
        if not name:
            self._show_error("Введите название категории.")
            return
        try:
            self._service.add_category(name)
        except PasswordManagerError as exc:
            self._show_error(str(exc))
            return
        self.new_name.clear()
        self._hide_error()
        self._refresh()
        self.changed.emit()

    def _rename(self, category_id: str, current: str) -> None:
        name = TextInputDialog.get_text(self, "Переименовать категорию", "Новое название", current)
        if not name or name == current:
            return
        try:
            self._service.rename_category(category_id, name)
        except PasswordManagerError as exc:
            MessageDialog.show_error(self, "Не удалось переименовать категорию", str(exc))
            return
        self._refresh()
        self.changed.emit()

    def _delete(self, category_id: str, name: str) -> None:
        if not ConfirmDialog.ask(
            self,
            "Удалить категорию?",
            f"Категория «{name}» будет удалена. Все её записи будут перенесены в «Другое». "
            "Действие нельзя отменить.",
            "Удалить",
            danger=True,
        ):
            return
        try:
            self._service.delete_category(category_id)
        except PasswordManagerError as exc:
            MessageDialog.show_error(self, "Не удалось удалить категорию", str(exc))
            return
        self._refresh()
        self.changed.emit()

    def _show_error(self, message: str) -> None:
        self.error.setText(message)
        self.error.show()
        self.adjustSize()

    def _hide_error(self) -> None:
        self.error.hide()
        self.adjustSize()
