"""Standalone password generator dialog."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QSlider,
    QSpinBox,
    QWidget,
)

from app.exceptions import GeneratorError
from app.services.clipboard_service import ClipboardService
from app.services.generator import (
    MAX_LENGTH,
    MIN_LENGTH,
    GeneratorOptions,
    estimate_strength,
    generate_password,
)
from app.ui.styles import TEXT_MUTED
from app.ui.widgets import (
    BaseDialog,
    IconButton,
    PrimaryButton,
    StrengthMeter,
    make_button,
    make_label,
    show_toast,
)


class GeneratorDialog(BaseDialog):
    password_selected = Signal(str)

    def __init__(
        self,
        clipboard: ClipboardService,
        clear_after: int = 30,
        select_mode: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent, "Генератор паролей", width=540, icon_name="key")
        self._clipboard = clipboard
        self._clear_after = clear_after
        self._select_mode = select_mode
        self._last_password = ""
        self._build()

    def _build(self) -> None:
        preview_row = QHBoxLayout()
        preview_row.setSpacing(8)
        self.preview = QLineEdit()
        self.preview.setObjectName("PasswordDisplay")
        self.preview.setReadOnly(True)
        self.preview.setMinimumHeight(52)
        preview_row.addWidget(self.preview, 1)
        regenerate = IconButton("refresh", "Сгенерировать заново", 40, 18)
        regenerate.clicked.connect(self._generate)
        preview_row.addWidget(regenerate)
        self.body.addLayout(preview_row)

        self.strength = StrengthMeter()
        self.body.addWidget(self.strength)

        self.error = make_label("", "Error", wrap=True)
        self.error.hide()
        self.body.addWidget(self.error)

        length_row = QHBoxLayout()
        length_row.addWidget(make_label("Длина пароля", "Caption"))
        length_row.addStretch(1)
        self.length_spin = QSpinBox()
        self.length_spin.setRange(MIN_LENGTH, MAX_LENGTH)
        self.length_spin.setValue(20)
        self.length_spin.setSuffix(" симв.")
        self.length_spin.setFixedWidth(112)
        length_row.addWidget(self.length_spin)
        self.body.addLayout(length_row)

        self.length_slider = QSlider(Qt.Orientation.Horizontal)
        self.length_slider.setRange(MIN_LENGTH, MAX_LENGTH)
        self.length_slider.setValue(20)
        self.length_slider.setPageStep(4)
        self.body.addWidget(self.length_slider)

        self.upper = QCheckBox("Заглавные буквы (A–Z)")
        self.lower = QCheckBox("Строчные буквы (a–z)")
        self.digits = QCheckBox("Цифры (0–9)")
        self.symbols = QCheckBox("Специальные символы (!@#$…)")
        for checkbox in (self.upper, self.lower, self.digits, self.symbols):
            checkbox.setChecked(True)

        options_widget = QWidget()
        grid = QGridLayout(options_widget)
        grid.setContentsMargins(0, 4, 0, 4)
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(10)
        grid.addWidget(self.upper, 0, 0)
        grid.addWidget(self.lower, 0, 1)
        grid.addWidget(self.digits, 1, 0)
        grid.addWidget(self.symbols, 1, 1)
        self.body.addWidget(options_widget)

        self.length_spin.valueChanged.connect(self._on_spin_changed)
        self.length_slider.valueChanged.connect(self._on_slider_changed)
        for checkbox in (self.upper, self.lower, self.digits, self.symbols):
            checkbox.toggled.connect(self._on_options_changed)

        self.footer.addWidget(
            make_button("Сгенерировать", "Ghost", "refresh", TEXT_MUTED)
        )
        generate_button = self.footer.itemAt(0).widget()
        generate_button.clicked.connect(self._generate)
        self.footer.addStretch(1)

        copy_button = make_button("Копировать", "Ghost", "copy", TEXT_MUTED)
        copy_button.clicked.connect(self._copy)
        self.footer.addWidget(copy_button)
        self.copy_button = copy_button

        if self._select_mode:
            use_button = PrimaryButton("Использовать", "check")
            use_button.clicked.connect(self._use)
            self.footer.addWidget(use_button)
            self.use_button = use_button
        else:
            close_button = PrimaryButton("Готово", "check")
            close_button.clicked.connect(self.accept)
            self.footer.addWidget(close_button)
            self.use_button = None

        self._generate()

    def _options(self) -> GeneratorOptions:
        return GeneratorOptions(
            length=self.length_spin.value(),
            uppercase=self.upper.isChecked(),
            lowercase=self.lower.isChecked(),
            digits=self.digits.isChecked(),
            symbols=self.symbols.isChecked(),
        )

    def _on_spin_changed(self, value: int) -> None:
        self.length_slider.blockSignals(True)
        self.length_slider.setValue(value)
        self.length_slider.blockSignals(False)
        self._generate()

    def _on_slider_changed(self, value: int) -> None:
        self.length_spin.blockSignals(True)
        self.length_spin.setValue(value)
        self.length_spin.blockSignals(False)
        self._generate()

    def _on_options_changed(self) -> None:
        self._generate()

    def _generate(self) -> None:
        try:
            password = generate_password(self._options())
            error = ""
        except GeneratorError as exc:
            password = ""
            error = str(exc)
        if error:
            self.error.setText(error)
            self.error.show()
            self.copy_button.setEnabled(False)
            if self.use_button is not None:
                self.use_button.setEnabled(False)
            self.strength.clear()
            self.preview.setText("")
            self._last_password = ""
            self.adjustSize()
            return

        self.error.hide()
        self.copy_button.setEnabled(True)
        if self.use_button is not None:
            self.use_button.setEnabled(True)
        self._last_password = password
        self.preview.setText(password)
        self.preview.setCursorPosition(0)
        self.strength.set_result(estimate_strength(password, generated=True))
        self.adjustSize()

    def _copy(self) -> None:
        if not self._last_password:
            return
        self._clipboard.copy_secret(self._last_password, self._clear_after)
        if self._clear_after > 0:
            show_toast(
                self,
                f"Пароль скопирован · буфер очистится через {self._clear_after} с",
                "success",
            )
        else:
            show_toast(self, "Пароль скопирован в буфер обмена", "success")

    def _use(self) -> None:
        if not self._last_password:
            return
        self.password_selected.emit(self._last_password)
        self.accept()

    def done(self, result: int) -> None:
        self.preview.clear()
        self._last_password = ""
        super().done(result)


def open_generator(
    parent: QWidget | None,
    clipboard: ClipboardService,
    clear_after: int,
    select_mode: bool = False,
) -> str | None:
    dialog = GeneratorDialog(clipboard, clear_after, select_mode, parent)
    selected: list[str] = []
    dialog.password_selected.connect(selected.append)
    dialog.exec()
    if selected:
        return selected[0]
    return None
