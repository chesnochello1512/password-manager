"""Reusable widgets for the dark Password Manager interface."""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QCursor, QFont, QPainter
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.models import PasswordRecord
from app.services.generator import StrengthResult
from app.ui import icons
from app.ui.styles import (
    ACCENT,
    AVATAR_COLORS,
    DANGER,
    SUCCESS,
    TEXT_MUTED,
    TEXT_SECONDARY,
    WARNING,
)


def make_label(text: str = "", object_name: str = "", wrap: bool = False) -> QLabel:
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    if object_name:
        label.setObjectName(object_name)
    label.setWordWrap(wrap)
    return label


def make_button(
    text: str,
    variant: str = "",
    icon_name: str | None = None,
    icon_color: str = TEXT_SECONDARY,
) -> QPushButton:
    button = QPushButton(text)
    if variant:
        button.setObjectName(variant)
    if icon_name:
        button.setIcon(icons.icon(icon_name, icon_color, 17))
        button.setIconSize(QSize(17, 17))
    button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    return button


class IconButton(QPushButton):
    def __init__(
        self,
        icon_name: str,
        tooltip: str = "",
        size: int = 32,
        icon_size: int = 18,
        color: str = TEXT_SECONDARY,
        object_name: str = "IconButton",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName(object_name)
        self.setFixedSize(size, size)
        self.setIconSize(QSize(icon_size, icon_size))
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setToolTip(tooltip)
        self.set_icon(icon_name, color)

    def set_icon(self, name: str, color: str = TEXT_SECONDARY) -> None:
        self.setIcon(icons.icon(name, color, self.iconSize().width()))


class PrimaryButton(QPushButton):
    def __init__(
        self,
        text: str,
        icon_name: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self.setObjectName("Primary")
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        if icon_name:
            self.setIcon(icons.icon(icon_name, "#0A1020", 17))
            self.setIconSize(QSize(17, 17))
        self.setMinimumHeight(38)


class SearchInput(QLineEdit):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SearchInput")
        self.setPlaceholderText("Поиск по названию, логину или сайту…")
        self.setClearButtonEnabled(False)
        self.setMinimumHeight(38)
        self.setMaximumWidth(520)
        self.addAction(icons.icon("search", TEXT_MUTED, 17), QLineEdit.ActionPosition.LeadingPosition)
        self._clear_action = self.addAction(
            icons.icon("x", TEXT_MUTED, 14), QLineEdit.ActionPosition.TrailingPosition
        )
        self._clear_action.setVisible(False)
        self._clear_action.triggered.connect(self._clear)
        self.textChanged.connect(lambda text: self._clear_action.setVisible(bool(text)))

    def _clear(self) -> None:
        self.clear()
        self.setFocus()


class PasswordLineEdit(QLineEdit):
    """Password input with a reveal action that hides itself again."""

    def __init__(self, placeholder: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setEchoMode(QLineEdit.EchoMode.Password)
        self.setPlaceholderText(placeholder)
        self.setMinimumHeight(42)
        self._visible = False
        self._action = self.addAction(
            icons.icon("eye", TEXT_MUTED, 18), QLineEdit.ActionPosition.TrailingPosition
        )
        self._action.setToolTip("Показать пароль")
        self._action.triggered.connect(self.toggle_visibility)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide_password)

    @property
    def visible_text(self) -> bool:
        return self._visible

    def toggle_visibility(self) -> None:
        if self._visible:
            self.hide_password()
        else:
            self.show_password()

    def show_password(self, seconds: int = 20) -> None:
        self._visible = True
        self.setEchoMode(QLineEdit.EchoMode.Normal)
        self._action.setIcon(icons.icon("eye-off", ACCENT, 18))
        self._action.setToolTip("Скрыть пароль")
        if seconds > 0:
            self._hide_timer.start(seconds * 1000)

    def hide_password(self) -> None:
        self._visible = False
        self._hide_timer.stop()
        self.setEchoMode(QLineEdit.EchoMode.Password)
        self._action.setIcon(icons.icon("eye", TEXT_MUTED, 18))
        self._action.setToolTip("Показать пароль")


class Chip(QLabel):
    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("Chip")
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)


class Avatar(QLabel):
    def __init__(self, size: int = 38, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._size = size
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setFont(QFont("Segoe UI", max(10, size // 3), QFont.Weight.DemiBold))

    def set_title(self, title: str) -> None:
        letter = icons.avatar_icon(title)
        background, foreground = AVATAR_COLORS[sum(ord(char) for char in title) % len(AVATAR_COLORS)]
        self.setText(letter)
        self.setStyleSheet(
            f"background: {background}; color: {foreground}; border-radius: {self._size // 2}px;"
            f"font-size: {max(12, self._size // 3)}px; font-weight: 600;"
        )


class SidebarItem(QFrame):
    clicked = Signal(str)

    def __init__(
        self,
        key: str,
        text: str,
        icon_name: str,
        count: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.key = key
        self.setObjectName("SidebarItem")
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setProperty("hovered", False)
        self.setProperty("selected", False)
        self.setFixedHeight(38)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(10)
        self._icon = QLabel()
        self._icon.setFixedSize(18, 18)
        self._icon.setPixmap(icons.pixmap(icon_name, TEXT_MUTED, 18))
        self._icon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._icon_name = icon_name
        layout.addWidget(self._icon)

        self.text_label = QLabel(text)
        self.text_label.setObjectName("SidebarText")
        self.text_label.setTextFormat(Qt.TextFormat.PlainText)
        self.text_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(self.text_label, 1)

        self.count_label = QLabel()
        self.count_label.setObjectName("CountBadge")
        self.count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.count_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(self.count_label)
        self.set_count(count)

    def set_count(self, count: int | None) -> None:
        if count is None:
            self.count_label.hide()
            return
        self.count_label.setText(str(count))
        self.count_label.setVisible(count > 0)

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        self.text_label.setProperty("selected", selected)
        color = ACCENT if selected else TEXT_MUTED
        self._icon.setPixmap(icons.pixmap(self._icon_name, color, 18))
        self._repolish()

    def _repolish(self) -> None:
        for widget in (self, self.text_label):
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    def enterEvent(self, event) -> None:  # noqa: N802
        self.setProperty("hovered", True)
        self._repolish()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.setProperty("hovered", False)
        self._repolish()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit(self.key)
        super().mouseReleaseEvent(event)


class RecordCard(QFrame):
    clicked = Signal(str)
    star_clicked = Signal(str)

    def __init__(self, record: PasswordRecord, category_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.record_id = record.id
        self.setObjectName("RecordCard")
        self.setProperty("selected", False)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFixedHeight(66)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 9, 10, 9)
        layout.setSpacing(11)

        avatar = Avatar(40)
        avatar.set_title(record.title)
        avatar.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(avatar)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)
        title = make_label(record.title, "CardTitle")
        title.setToolTip(record.title)
        title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        subtitle_text = record.username or record.url or category_name or "Без логина"
        subtitle = make_label(subtitle_text, "CardSubtitle")
        subtitle.setToolTip(subtitle_text)
        subtitle.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        text_layout.addWidget(title)
        text_layout.addWidget(subtitle)
        layout.addLayout(text_layout, 1)

        self.star = IconButton(
            "star-filled" if record.favorite else "star",
            "Убрать из избранного" if record.favorite else "Добавить в избранное",
            28,
            16,
            WARNING if record.favorite else TEXT_MUTED,
        )
        self.star.clicked.connect(lambda: self.star_clicked.emit(self.record_id))
        layout.addWidget(self.star, 0, Qt.AlignmentFlag.AlignTop)

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.record_id)
        super().mouseReleaseEvent(event)


class FieldRow(QFrame):
    copy_requested = Signal(str)

    def __init__(
        self,
        caption: str,
        value: str,
        copyable: bool = True,
        monospace: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._value = value
        self.setObjectName("FieldRow")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 10, 10)
        layout.setSpacing(12)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(3)
        text_layout.addWidget(make_label(caption, "FieldCaption"))
        value_label = make_label(value if value else "—", "FieldValue", wrap=True)
        value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        if monospace:
            value_label.setFont(QFont("Cascadia Mono", 10))
        if not value:
            value_label.setObjectName("Muted")
        text_layout.addWidget(value_label)
        layout.addLayout(text_layout, 1)

        if copyable and value:
            copy_button = IconButton("copy", "Копировать", 30, 16)
            copy_button.clicked.connect(lambda: self.copy_requested.emit(self._value))
            layout.addWidget(copy_button, 0, Qt.AlignmentFlag.AlignVCenter)


class StrengthBars(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._score = -1
        self.setFixedHeight(6)
        self.setMinimumWidth(120)

    def set_score(self, score: int) -> None:
        self._score = max(0, min(4, score))
        self.update()

    def reset(self) -> None:
        self._score = -1
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(DANGER if self._score <= 1 else WARNING if self._score == 2 else SUCCESS)
        gap = 4
        segment = (self.width() - gap * 3) / 4
        painter.setPen(Qt.PenStyle.NoPen)
        for index in range(4):
            if 0 <= self._score and index <= self._score:
                painter.setBrush(color)
            else:
                painter.setBrush(QColor("#252C39"))
            painter.drawRoundedRect(
                QRectF(index * (segment + gap), 0, segment, self.height()), 2, 2
            )
        painter.end()


class StrengthMeter(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.bars = StrengthBars()
        self.caption = make_label("Надёжность: —", "MutedSmall")
        layout.addWidget(self.bars)
        layout.addWidget(self.caption)

    def set_result(self, result: StrengthResult) -> None:
        self.bars.set_score(result.score)
        if result.generated:
            caption = (
                f"Надёжность: {result.label} · ≈{result.entropy_bits:.0f} бит "
                "(оценка генератора)"
            )
        else:
            caption = f"Надёжность: {result.label}"
            if result.warning:
                caption += f" · {result.warning}"
        self.caption.setText(caption)

    def clear(self) -> None:
        self.bars.reset()
        self.caption.setText("Надёжность: —")


class EmptyState(QWidget):
    def __init__(
        self,
        icon_name: str,
        title: str,
        description: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(10)
        layout.addStretch(1)

        badge = QLabel()
        badge.setObjectName("IconBadge")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setPixmap(icons.pixmap(icon_name, ACCENT, 30))
        badge.setFixedSize(58, 58)
        badge_row = QHBoxLayout()
        badge_row.addStretch(1)
        badge_row.addWidget(badge)
        badge_row.addStretch(1)
        layout.addLayout(badge_row)

        title_label = make_label(title, "CardTitle")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("font-size: 15px;")
        layout.addWidget(title_label)

        if description:
            description_label = make_label(description, "Muted", wrap=True)
            description_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            description_label.setMaximumWidth(320)
            row = QHBoxLayout()
            row.addStretch(1)
            row.addWidget(description_label)
            row.addStretch(1)
            layout.addLayout(row)

        layout.addStretch(1)


class DragHeader(QFrame):
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self.window().windowHandle()
            if handle is not None:
                handle.startSystemMove()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        window = self.window()
        if isinstance(window, QDialog):
            super().mouseDoubleClickEvent(event)
            return
        if window.isMaximized():
            window.showNormal()
        else:
            window.showMaximized()
        super().mouseDoubleClickEvent(event)


class BaseDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None,
        title: str,
        width: int = 560,
        icon_name: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 18, 18, 18)
        self.surface = QFrame()
        self.surface.setObjectName("DialogSurface")
        shadow = QGraphicsDropShadowEffect(self.surface)
        shadow.setBlurRadius(46)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 150))
        self.surface.setGraphicsEffect(shadow)
        outer.addWidget(self.surface)

        inner = QVBoxLayout(self.surface)
        inner.setContentsMargins(0, 0, 0, 0)
        inner.setSpacing(0)

        header = DragHeader()
        header.setFixedHeight(60)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(22, 0, 16, 0)
        header_layout.setSpacing(10)
        if icon_name:
            badge = QLabel()
            badge.setObjectName("IconBadge")
            badge.setFixedSize(32, 32)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setPixmap(icons.pixmap(icon_name, ACCENT, 18))
            header_layout.addWidget(badge)
        header_layout.addWidget(make_label(title, "DialogTitle"))
        header_layout.addStretch(1)
        close_button = IconButton("x", "Закрыть", 30, 16)
        close_button.clicked.connect(self.reject)
        header_layout.addWidget(close_button)
        self.close_button = close_button
        inner.addWidget(header)

        body_widget = QWidget()
        self.body = QVBoxLayout(body_widget)
        self.body.setContentsMargins(24, 4, 24, 8)
        self.body.setSpacing(14)
        inner.addWidget(body_widget, 1)

        footer_widget = QWidget()
        self.footer = QHBoxLayout(footer_widget)
        self.footer.setContentsMargins(24, 12, 24, 22)
        self.footer.setSpacing(10)
        inner.addWidget(footer_widget)

        self.setFixedWidth(width + 36)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.adjustSize()
        parent = self.parentWidget()
        if parent is not None:
            screen = parent.window().geometry()
            self.move(
                screen.center().x() - self.width() // 2,
                screen.center().y() - self.height() // 2,
            )
        elif self.screen() is not None:
            screen = self.screen().availableGeometry()
            self.move(
                screen.center().x() - self.width() // 2,
                screen.center().y() - self.height() // 2,
            )


class ConfirmDialog(BaseDialog):
    def __init__(
        self,
        parent: QWidget | None,
        title: str,
        message: str,
        confirm_text: str = "Подтвердить",
        danger: bool = True,
    ) -> None:
        super().__init__(parent, title, width=470, icon_name="warning" if danger else "info")
        message_label = make_label(message, "", wrap=True)
        message_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 13px;")
        self.body.addWidget(message_label)

        self.footer.addStretch(1)
        cancel = make_button("Отмена", "Ghost")
        cancel.clicked.connect(self.reject)
        self.footer.addWidget(cancel)
        confirm = PrimaryButton(confirm_text)
        if danger:
            confirm.setObjectName("Danger")
            confirm.setIcon(icons.icon("trash", DANGER, 17))
        else:
            confirm.setIcon(icons.icon("check", "#0A1020", 17))
        confirm.clicked.connect(self.accept)
        self.footer.addWidget(confirm)

    @classmethod
    def ask(
        cls,
        parent: QWidget | None,
        title: str,
        message: str,
        confirm_text: str = "Подтвердить",
        danger: bool = True,
    ) -> bool:
        dialog = cls(parent, title, message, confirm_text, danger)
        return dialog.exec() == QDialog.DialogCode.Accepted


class MessageDialog(BaseDialog):
    def __init__(self, parent: QWidget | None, title: str, message: str, kind: str = "info") -> None:
        icon_name = "warning" if kind == "error" else "check" if kind == "success" else "info"
        super().__init__(parent, title, width=470, icon_name=icon_name)
        label = make_label(message, "", wrap=True)
        label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 13px;")
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.body.addWidget(label)
        self.footer.addStretch(1)
        button = PrimaryButton("Понятно")
        button.clicked.connect(self.accept)
        self.footer.addWidget(button)

    @classmethod
    def show_info(cls, parent: QWidget | None, title: str, message: str) -> None:
        cls(parent, title, message, "info").exec()

    @classmethod
    def show_error(cls, parent: QWidget | None, title: str, message: str) -> None:
        cls(parent, title, message, "error").exec()

    @classmethod
    def show_success(cls, parent: QWidget | None, title: str, message: str) -> None:
        cls(parent, title, message, "success").exec()


class TextInputDialog(BaseDialog):
    def __init__(
        self,
        parent: QWidget | None,
        title: str,
        caption: str,
        initial: str = "",
        placeholder: str = "",
    ) -> None:
        super().__init__(parent, title, width=440, icon_name="edit")
        self.body.addWidget(make_label(caption, "Caption"))
        self.input = QLineEdit(initial)
        self.input.setPlaceholderText(placeholder)
        self.input.setMinimumHeight(40)
        self.input.returnPressed.connect(self._accept)
        self.body.addWidget(self.input)
        self.error = make_label("", "Error", wrap=True)
        self.error.hide()
        self.body.addWidget(self.error)

        self.footer.addStretch(1)
        cancel = make_button("Отмена", "Ghost")
        cancel.clicked.connect(self.reject)
        self.footer.addWidget(cancel)
        save = PrimaryButton("Сохранить", "check")
        save.clicked.connect(self._accept)
        self.footer.addWidget(save)

    def _accept(self) -> None:
        value = " ".join(self.input.text().split())
        if not value:
            self.error.setText("Значение не может быть пустым.")
            self.error.show()
            self.adjustSize()
            return
        self.accept()

    def value(self) -> str:
        return self.input.text()

    @classmethod
    def get_text(
        cls,
        parent: QWidget | None,
        title: str,
        caption: str,
        initial: str = "",
        placeholder: str = "",
    ) -> str | None:
        dialog = cls(parent, title, caption, initial, placeholder)
        dialog.input.selectAll()
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return " ".join(dialog.input.text().split())
        return None


class Toast(QFrame):
    def __init__(self, parent: QWidget, text: str, kind: str, duration: int) -> None:
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setProperty("kind", kind)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 9, 14, 9)
        layout.setSpacing(9)
        icon_name = {"success": "check", "error": "x", "warning": "warning"}.get(kind, "info")
        color = {"success": SUCCESS, "error": DANGER, "warning": WARNING}.get(kind, ACCENT)
        icon_label = QLabel()
        icon_label.setPixmap(icons.pixmap(icon_name, color, 16))
        layout.addWidget(icon_label)
        layout.addWidget(make_label(text, "ToastText"))
        self.adjustSize()
        self._duration = duration
        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(0.0)
        self.setGraphicsEffect(self._effect)
        self._animation = QPropertyAnimation(self._effect, b"opacity", self)
        self._animation.setDuration(160)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fade_out)
        self._position()

    def _position(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        margin = 22
        x = max(margin, parent.width() - self.width() - margin)
        y = max(margin, parent.height() - self.height() - margin)
        self.move(x, y)

    def start(self) -> None:
        self.show()
        self.raise_()
        self._animation.start()
        self._timer.start(self._duration)

    def _fade_out(self) -> None:
        self._animation.stop()
        self._animation.setStartValue(self._effect.opacity())
        self._animation.setEndValue(0.0)
        self._animation.setDuration(220)
        self._animation.finished.connect(self.deleteLater)
        self._animation.start()


def show_toast(parent: QWidget | None, text: str, kind: str = "info", duration: int = 3200) -> None:
    if parent is None:
        return
    target = parent.window() if parent.window() is not None else parent
    previous = getattr(target, "_active_toast", None)
    if previous is not None:
        try:
            previous.deleteLater()
        except RuntimeError:
            pass
    toast = Toast(target, text, kind, duration)
    setattr(target, "_active_toast", toast)  # noqa: B010 - Qt object has no declared attribute
    toast.start()


__all__ = [
    "Avatar",
    "BaseDialog",
    "Chip",
    "ConfirmDialog",
    "EmptyState",
    "FieldRow",
    "IconButton",
    "MessageDialog",
    "PasswordLineEdit",
    "PrimaryButton",
    "RecordCard",
    "SearchInput",
    "SidebarItem",
    "StrengthMeter",
    "TextInputDialog",
    "Toast",
    "make_button",
    "make_label",
    "show_toast",
]
